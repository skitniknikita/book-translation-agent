# Translation Protocol

## Objective

Translate philosophical and humanities texts from the language of the supplied original into natural Russian, preserving the original's argument, terminology, and structure. The result must be suitable for reading and EPUB publication, rather than remaining a literal crib.

The user need not understand formats or publishing tools. Make technical decisions independently provided they do not change the book's content.

### Priorities

1. Meaning and the original's logical distinctions.
2. Terminological consistency with the Russian tradition.
3. Natural Russian syntax and style.
4. Complete structure: paragraphs, quotations, footnotes, captions, and bibliography.
5. Functional final files.

Do not make the author clearer, more categorical, or more logical than they are. Preserve productive ambiguity, but do not mistake it for careless calque.

## What Counts as Complete

The full cycle is complete only when:

- a researched glossary was created before translation;
- all authorial text has been translated;
- meaning, language, and terminology checks have been performed;
- disputed decisions are explicitly marked;
- the EPUB was rebuilt and checked after the latest revisions;
- the user was given exact file paths and any limitations.

---

## Workflow

| Stage | Result | Quality gate |
|---|---|---|
| 1. Source intake | The text's contents and boundaries are understood | The source is suitable for analysis |
| 2. Term extraction | A complete list of difficult concepts | The entire text has been reviewed |
| 3. Research | `00_Глоссарий.md` | A decision is made or flagged for key terms |
| 4. Translation | `01_Перевод.md` | All semantic blocks are translated |
| 5. Editing | Checked Russian text | Three editorial passes are complete |
| 6. Publication | `Автор — Название.epub` | The EPUB is structurally and substantively checked |

Do not begin the main translation until a working glossary exists.

---

## 1. Source Intake

For a new work, determine:

- author, title, language, and edition;
- the extent and boundaries of the authorial text;
- headings and internal structure;
- footnotes, notes, quotations, and bibliography;
- tables, formulas, lists, and illustrations;
- information about the author, source, and rights.

When extracting from PDF, EPUB, DOCX, or OCR, check the beginning, middle, and end against the original. Pay particular attention to line breaks, ligatures, quotation marks, footnotes, and words in third languages.

Remove website menus, advertising, and navigation, but preserve publication metadata. Do not alter or delete the local source.

If a phrase is damaged or erroneous in the original itself, do not silently correct its meaning: record the chosen reading and alternative in the glossary or a translator's note.

### When to Ask the User

Stop and ask one specific question only when:

- the source is missing or incomplete;
- the text cannot be reconstructed reliably;
- materially different editions exist and it is unclear which to translate;
- one global decision would affect the entire book and sources do not permit an independent choice.

In all other cases, make reversible decisions independently and continue.

---

## 2. Glossary and Terminology Research

The required sequence is: first read the entire text and extract terms with context, then verify them online, then approve a working glossary. Internet research cannot be replaced by model memory or a single search for a ready-made glossary. Earlier local glossaries are a starting point, not proof that each rendition has been published.

For each key or disputed term, search for and open the sources found. Give priority to published translations of the author, publishers' pages and excerpts, academic journals, universities, and official libraries. A site's official status alone does not establish the required meaning: verify the precise use, edition, author or translator, page/section, and philosophical context. A search-engine snippet, automatically compiled dictionary, or another AI's answer does not count as a read source.

For confirmation, preserve the direct link, title, access date, page or section, and a brief description of the evidence. If no confirmation is found after searching, record the queries/sources checked, the working rendering, and the uncertainty; do not give the rendering established status. A conventional rendering requires disciplinary evidence, not the model's confident tone.

If internet access or source access is unavailable for the whole verification process, continue extracting terms and preparing the work, but report the blocker before the main translation. Continuing without research is permitted only by the user's explicit decision, with the glossary marked as provisional and its quality limitation stated.

### What to Extract

Read the entire work and list:

- authorial concepts and neologisms;
- philosophical, scientific, and technical terms;
- conceptual pairs and oppositions;
- multiword formulas;
- ordinary words with specialized meanings;
- words whose meaning changes within the text;
- terms with competing Russian renderings;
- names, titles of works, theories, and thought experiments;
- repetitions and wordplay that carry the argument.

Do not add ordinary vocabulary without conceptual weight. The glossary must be exhaustive for concepts, not maximized for its number of rows.

If a term changes meaning, create separate context-specific decisions. Do not impose a single equivalent on an author's polysemy.

### Where to Verify a Russian Rendering

Use sources in this order:

1. Published Russian translations of the same author.
2. Official publishers and lawful book excerpts.
3. Russian translations of thinkers cited by the author.
4. Academic journals, universities, and scholarly databases.
5. Professional translations of essays, interviews, and lectures.
6. Independent articles, only as supplementary evidence.

First check the glossaries of already translated works by the same author in this folder. Retain an earlier decision unless the new context requires a departure.

A completed translation of the same text may be used to compare terminology, but translate the original supplied by the user independently.

For each web source, preserve the direct link, title, and access date. Several identical paraphrases do not count as independent confirmation.

### How to Make a Decision

Give every rendering a status:

- **Fixed** — published for this author or in a canonical translation of a cited thinker.
- **Conventional** — accepted in the Russian-language discipline.
- **Working** — proposed for this text and requiring justification.

Also state confidence: high, medium, or low.

When sources disagree, compare the meaning in the paragraph, the concept's place in the author's system, its connection to the tradition, the prevalence of each rendering, and preservation of important oppositions.

### Structure of `00_Глоссарий.md`

1. Translation principles for this text.
2. Main glossary.
3. Names and accepted titles of works.
4. Sources for terminology verification.
5. Decisions requiring editorial attention.

For every term, include:

| Original | Context | Main translation | Alternatives | Status | Rationale | Confidence | Sources |
|---|---|---|---|---|---|---|---|

If the full cycle was requested, continue automatically after saving the glossary. If the user requested terminology research only, stop after the glossary.

---

## 3. Translation

### Accuracy and Russian

- Preserve claims, qualifications, negations, modality, and logical transitions.
- Recast the original sentence according to Russian syntax.
- Do not replace a difficult concept with a familiar word when that loses a distinction.
- Do not remove conceptually meaningful repetition for stylistic variety.
- Do not insert explanations into the author's voice: use a footnote or note.
- Do not mechanically unify `technology`, `technics`, and `technical`; distinguish «технику», «технологию», «техническое», and «технологическое» from context.

### Ambiguous Terms

- Use a canonical Russian term without a duplicate in the original language.
- If Russian erases a significant distinction, add a short clarification at first use: `исчисление [расчёт]`.
- Do not put stylistic synonyms in parentheses. Parentheses are for semantic ambiguity only and normally appear once.
- If a term's translation changes by context, describe this in advance in the glossary.

### Quotations and Titles

- Use the published Russian title of a work when one is established.
- For a quotation from an existing Russian edition, use the published translation where possible and cite its source.
- Do not present your own translation of a quotation as the text of a Russian edition.
- When the Russian form of a rare name or term is unstable, retain the original at its first occurrence.

### Original Structure

Preserve the order and boundaries of headings, paragraphs, lists, quotations, footnotes, tables, formulas, captions, and information about the author and source.

You may split or combine a paragraph only for natural Russian syntax, provided the composition of the argument remains unchanged.

---

## 4. Editing and Checking

Perform three independent passes.

### A. Meaning Check

Check every semantic block, omissions and additions, negations, degree of categorical force, pronoun references, numbers, dates, names, quotations, footnotes, and captions.

Compare counts of semantic blocks, lists, captions, and notes. Counters help detect an omission but do not replace manual comparison.

### B. Editing the Russian Text

Remove calqued word order, superfluous pronouns and passives, incorrect government, accidental repetitions, bureaucratic language alien to the author, and overloaded constructions created by the original's syntax.

After revisions, reread the text as an independent Russian work without looking at the original.

### C. Terminology Check

- Search the translation for terms from the glossary.
- Find undesirable competing renderings.
- Explain every deliberate departure from the glossary.
- Compare the text with earlier translations of the same author.
- When a decision changes, update the glossary, every occurrence, notes, and the EPUB.

---

## 5. Project Files

Store each work separately:

```text
Автор — Название/
├── 00_Глоссарий.md
├── 01_Перевод.md
├── 02_Примечания_переводчика.md   # only when needed
├── assets/                        # only when materials exist
├── metadata.yaml
├── epub.css
└── Автор — Название.epub
```

Do not create empty files or folders merely for the template. After saving, report exact absolute paths.

---

## 6. EPUB

In the full cycle, EPUB is included by default. Include:

- a title page and table of contents;
- the glossary before the translation;
- main text with footnotes;
- information about the author;
- the original source and rights information.

Do not create the impression of an official published translation.

Add images only when files are available and their use is permissible. If only captions are supplied, preserve them and report the absence of images.

After every final build, check:

1. ZIP-container integrity;
2. the presence of the OPF, navigation, title page, and all sections;
3. XML/XHTML validity;
4. that the EPUB can be read back;
5. the glossary, beginning, and final paragraph of the translation;
6. the table of contents and footnotes;
7. language, author, title, and rights metadata.

After changing Markdown, rebuild the EPUB and repeat the relevant checks.

---

## 7. Communication and Autonomy

At the start of a book or complex essay, briefly state the scope, preserved elements, and real uncertainties. If everything is unambiguous, do not wait for formal confirmation.

During lengthy work, report only meaningful transitions: source parsed, glossary researched, translation complete, EPUB checked.

In the final response, begin with the result and link the glossary, translation, and EPUB. Then state the checks performed and remaining limitations.

If the user changes a terminological decision, update not only one phrase but also the glossary, all related occurrences, and the EPUB.

---

## Final Gates

Before completion, confirm:

- [ ] Authorial text is separated from service elements.
- [ ] The glossary was created before translation and confirmed by sources.
- [ ] Key terms have a status and confidence level.
- [ ] The translation follows the glossary.
- [ ] All semantic blocks and structural elements are preserved.
- [ ] Three editorial passes are complete.
- [ ] Terminological exceptions are explained.
- [ ] The EPUB was rebuilt after the latest changes and checked.
- [ ] The user received exact paths and an honest account of limitations.
