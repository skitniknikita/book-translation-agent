# Book Translation Agent

English | [Русский](README.ru.md)

A research-first book translation workflow for Codex. A capable lead model researches terminology and checks every passage against the original. Smaller models draft and copyedit; Python scripts preserve progress and assemble the EPUB.

Designed for philosophy and humanities books, with **Russian as the default translation language**. Project documentation and agent instructions are in English. Russian terminology examples, output filenames, and some script messages are retained. This is an independent project, not an official OpenAI product.

**Status:** early release. Local tests cover workflow bookkeeping and EPUB assembly. Full-book savings, translation quality across model combinations, and end-to-end operation on other machines have not been benchmarked.

## What you get

- **A researched glossary before translation.** The agent examines the full source, checks prior translations of the author, and researches published translations, publishers, and academic sources online. Decisions include evidence, context, alternatives, and confidence.
- **Large-model supervision.** Smaller workers handle bounded assignments. The lead approves terminology, resolves difficult passages, and performs the complete semantic comparison. There are at most two concurrent workers.
- **Model selection per book.** The agent uses the current Codex catalog and official documentation, then tests the chosen pair on ordinary and difficult passages. A catalog entry alone does not prove access or translation quality.
- **Resumable work.** Source blocks, tasks, drafts, edits, review evidence, and accepted summaries are saved. Changes invalidate affected checks.
- **A checked EPUB.** Pandoc assembles the accepted text, glossary, notes, and publication metadata. Failed builds preserve the previous output.

The scripts perform bookkeeping and assembly. Research, translation, and editorial judgment still require the models and, when appropriate, a human editor.

## Start in the Codex app

1. Download this repository with **Code → Download ZIP**, then extract it. Keep the hidden `.agents` and `.codex` directories.
2. Open the extracted directory as a Codex project. Review its instructions before trusting it. Project configuration loads only for trusted projects; see [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-basic#configuration-precedence).
3. Create a `books` folder inside it and place a book there. That folder is ignored by Git. Keep previous author glossaries there too, if available.
4. Choose an available high-capability model and send this prompt:

```text
Use $translate-book to translate books/my-book.epub into Russian and produce an EPUB.
Keep all outputs in books/my-book-output. First inspect the full source and research
the glossary using published translations and authoritative sources online.
Check the currently available models: a capable lead model must supervise smaller
workers and compare every passage with the source. Use the bundled workflow scripts
to save progress. Preserve the original file.
```

Replace `my-book.epub` with your filename. If the skill is not discovered, ask Codex to read [.agents/skills/translate-book/SKILL.md](.agents/skills/translate-book/SKILL.md). To try a small, original sample first, see [examples](examples/README.md).

An instruction cannot change the model of an already open chat. If selection calls for a different lead model, select it in the app when the agent asks. The CLI launcher can start a new session with the selected model.

## Requirements

| Component | Needed for |
| --- | --- |
| Codex with a signed-in account, web search, and subagents | Research and translation |
| Python 3.11 or later | Launcher and workflow scripts; standard library only |
| Pandoc on `PATH` | EPUB assembly and the full test suite |
| A current Codex CLI | The optional terminal launcher |

Use the official installation instructions for [Python](https://www.python.org/downloads/), [Codex CLI](https://learn.chatgpt.com/docs/codex/cli), and [Pandoc](https://pandoc.org/installing.html). No Python package installation or API key is required by the scripts. The project does not install tools or modify global Codex settings automatically.

The bootstrap model in [.codex/config.toml](.codex/config.toml) is only the starting point for selection. If your account cannot use it, choose an available high-capability model and update that local setting before running the launcher. Do not substitute a small model for the lead role. See [model selection](.agents/skills/translate-book/references/model-selection.md).

## Optional terminal launcher

Run these commands from the repository directory:

```sh
python3 launch.py --check
python3 launch.py --book "books/my-book.epub" --book-dir "books/my-book-output" --dry-run
python3 launch.py --book "books/my-book.epub" --book-dir "books/my-book-output"
```

`--check` checks local package configuration; it does not prove model access or Pandoc availability. `--dry-run` does not start a model. An ordinary run without a saved choice queries the catalog, starts a preparation session, validates its selection, and then starts the lead model. Preparation and translation use your Codex allowance. The launcher stops if preparation or validation fails.

Additional commands:

```sh
python3 launch.py --catalog
python3 launch.py --book "books/my-book.epub" --book-dir "books/my-book-output" --prepare
```

`--catalog` retrieves model metadata without text generation, but may contact Codex services. Its output can be cached and is not proof of inference access. Resuming keeps the saved model choice; a newly released model does not silently replace it. Without `--book-dir`, outputs go beside the source in a folder named `<source stem> — перевод`.

On Windows, Python may be invoked as `py -3`. The launcher requires a native `codex.exe`; `.cmd` and `.bat` wrappers are rejected. Windows and Linux live model sessions have not been verified. The locally tested older CLI exposed a limited catalog; a full session with the configured bootstrap model remains unverified.

## Workflow and outputs

```text
Inspect the complete source → research and approve the glossary
→ calibrate the selected models → draft in bounded assignments
→ semantic review + Russian copyedit + terminology review
→ assemble and validate the EPUB
```

Semantic review comes first by default. The alternative “copyedit, then semantic review” order requires a documented comparison on the first chapter. It is not enabled merely to save tokens. Subsequent edits invalidate affected reviews.

Each book has its own directory:

```text
books/my-book-output/
├── 00_Глоссарий.md       # Researched glossary
├── 01_Перевод.md         # Assembled translation
├── 03_Проверки.md        # Agent's verification report
├── metadata.json        # Title, author, language, source, rights, unofficial notice
├── book.epub
└── work/                # Source snapshot, model choice, tasks, versions, evidence
```

Translator notes, images, and CSS are added when needed. The agent writes editorial reports; the scripts do not invent evidence of reading or research. Illustrations are preserved and captions translated. Text inside diagrams is recognized and visually checked by the agent, then translated alongside the original; automatic image redrawing is not included.

To continue, ask: “Resume the book in `books/my-book-output` from its saved state. Check source integrity and which reviews are still current first.” A running Codex session is required; this is not a scheduled background service. Older manual schema-1 journals are not automatically migrated to the schema-2 workflow.

## Privacy and book rights

Keep originals, translations, and account-specific logs in `books/` or outside the repository. `.gitignore` excludes common generated files, but it is not a security boundary: review changes before committing. Codex model calls process book content through your configured service; the complete translation workflow is not offline. The standalone EPUB builder uses local resources.

Use texts you are authorized to process. Rights to the agent's code do not grant rights to books, quotations, images, or translations. Output must identify an unofficial translation and retain appropriate source information.

## Development and verification

With Python and Pandoc installed:

```sh
python3 -m unittest discover -s tests -v
python3 launch.py --check
python3 tools/release.py --check
```

Tests run without model calls, credentials, or a Codex installation. They check completeness, stale reviews, selection validation, edits, local resource handling, and real EPUB conversion and reverse reading through Pandoc. Synthetic review records test mechanics; they do not establish translation quality.

[GitHub Actions](.github/workflows/checks.yml) runs checks on Ubuntu with Python 3.11 and 3.12 after publication. It does not translate books, publish releases, or use model API keys. This workflow has not been run on GitHub yet.

| Location | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Lead and worker responsibilities |
| [SKILL.md](.agents/skills/translate-book/SKILL.md) | Translation workflow entry point |
| [Translation protocol](.agents/skills/translate-book/references/translation-protocol.md) | Research and editorial requirements |
| [Automation reference](.agents/skills/translate-book/references/automation.md) | Commands, records, and validation gates |
| [launch.py](launch.py) | Model selection and Codex session launch |
| [Workflow scripts](.agents/skills/translate-book/scripts/book_workflow.py) | State, packets, reviews, and assembly |
| [EPUB builder](.agents/skills/translate-book/scripts/epub_builder.py) | Offline conversion and structural checks |

See [CONTRIBUTING.md](CONTRIBUTING.md) for changes and [SECURITY.md](SECURITY.md) for sensitive reports. Maintainers can use the [publication guide](docs/PUBLISHING.md) or its [Russian version](docs/PUBLISHING.ru.md).

## Known limits

- Scanned PDFs and damaged extraction require separate OCR and inspection; there is no universal source parser bundled here.
- Scripts cannot prove semantic accuracy, source reliability, or that a model genuinely completed its assigned reading.
- ZIP, XML, navigation, links, metadata, and reverse-reading checks do not replace the complete EPUBCheck conformance suite.
- No measured full-book cost or subscription savings are claimed. Account-wide usage percentages cannot be attributed to one book; missing metrics remain unknown, not zero.

The workflow grew from a custom translation protocol. Discussions of [BookTrans](https://github.com/sukamenev/booktrans) informed work on saved state and compact context; its code and book texts are not included here.
