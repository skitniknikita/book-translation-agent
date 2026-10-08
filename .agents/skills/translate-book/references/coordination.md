# Coordination, Resumption, and Usage

For new books, state schema 2 and program commands are described in [automation](automation.md). The protocol below is retained for earlier schema 1 books and manual resumption. Do not present this journal as an automatic scheduler or silently migrate older books.

## Role Separation

| Role | Default model | Assignment | Approver |
|---|---|---|---|
| Lead | The large model selected for the book | Plan, research and term approval, difficult translation, complete meaning check, final result | Lead |
| Scout | The small model selected for the book | All blocks in its range, candidate terms, verifiable sources, risks | Lead |
| Draft translator | The small model selected for the book | Only the assigned passage, following approved decisions and preserving IDs and footnotes | Lead |
| Language editor | The small model selected for the book | An independent reading of the translation without the original; changes and questions only | Lead |

The same model in different contexts is not independent evidence of quality. The three passes are separated by task; they are not claimed to be three independent model families. Accountability and the meaning check remain with the lead. Use code for counters, checksums, and packaging where it is more reliable than a model.

## Assignment Contract

Before starting, give the worker:

1. Its role, language, expected result, and exact non-overlapping ID range.
2. The path to the assigned input and the only output files it may write.
3. Only the necessary terminology decisions, with the glossary version/hash.
4. A short argument summary, the current part, and, for translation, the end of the preceding part.
5. The requirement to preserve structure and report uncertainty without inventing content.
6. A prohibition on self-delegation and on changing shared files.

Exclude the source from the editor's assignment. First obtain its language edits; then compare those changes with the original yourself. Do not use the translator's context as the editor's context for the same passage.

The worker must return: processed IDs, output paths, and a list of omissions and doubts linked to IDs. A scout's response must include evidence and variants; a translator's, a draft and short summary; an editor's, IDs, “before”, “after”, and reason. The environment supplies metrics. Do not ask a model to guess its own tokens or name.

## Retry Limit

For an incomplete response, name the specific missing IDs and make no more than one targeted retry. On a repeated failure, diagnose the assignment size, source corruption, terminological uncertainty, or a model limit. Give difficult translation to the large model and record the reason. Do not blindly repeat the entire range or declare an incomplete response complete.

When a limit is exhausted, save the files and resumption point and tell the user. Do not automatically switch to a paid API or another model. Do not schedule background wake-ups without a separate instruction.

## Book State

`work/state.json` is a working journal maintained by the lead; it is not a separate automatic scheduler. Update it after accepting each passage and before ending a session. Write through a temporary file and atomic rename. Store paths relative to the book folder so that it remains portable.

Minimal structure:

```json
{
  "schema_version": 1,
  "book": {"source": "source/original.epub", "sha256": "<computed SHA-256>", "source_language": "fr", "target_language": "ru"},
  "glossary": {"path": "00_Глоссарий.md", "sha256": "<computed SHA-256>", "approved": true},
  "chunks": [{
    "id": "ch01-part01",
    "block_ids": ["ch01.p001", "ch01.p002"],
    "term_ids": ["term-001"],
    "source_sha256": "<computed SHA-256>",
    "glossary_sha256": "<hash of the approved glossary>",
    "translation": "work/translation/ch01-part01.md",
    "translation_sha256": "<computed SHA-256>",
    "stage": "draft",
    "reviews": {"meaning": null, "language": null, "terminology": null},
    "open_issues": ["ch01.p002: check the subject of the action"]
  }],
  "next_action": "Meaning check for ch01-part01",
  "epub": {"path": null, "input_sha256": null, "validated": false}
}
```

This is a structural example, not a ready record. Do not preserve angle-bracket placeholders in the actual journal. For every completed review, store the model/reviewer, date, hash of the reviewed version, ID range, and report path. If the model is not confirmed by metadata, state that. A file's presence does not mean it is complete.

On resumption, first compare hashes of the original, glossary, translation, and version reviewed by the editor. If the source changed, recheck affected blocks and their links. If the translation changed, previous checks do not confirm the new version. If the glossary changed, find every occurrence and affected summaries. If any build input changed, the EPUB must be rebuilt. Do not retranslate completed work merely because this is a new chat.

## Term Index

In `work/term-index.json`, retain for each stable term ID the original, context-specific meaning, discovered word forms/variants, source-block IDs, current translation, and hash of the approved decision. Mark the same ID in the glossary, for example in a separate column or anchor. Retain linked `term_ids` for each chunk.

Build the index while reviewing the entire text, not with one exact search. Update it for new occurrences and during editing. A changed global glossary hash triggers comparison of specific decisions and checking of linked blocks, summaries, and notes. With an incomplete index, recheck changed terms throughout the book: an absent string match does not prove an absent occurrence. Do not accept old completion marks for unchecked dependencies.

## Model and Usage Journal

The lead alone writes `work/usage.jsonl`. Use one record per completed task and a unique `task_id` so it is not counted twice:

```json
{"task_id":"draft-ch01-part01-attempt1","stage":"draft","agent_id":"<environment ID>","requested_model":"gpt-5.6-terra","observed_model":null,"reasoning":"high","input_tokens":null,"cached_input_tokens":null,"output_tokens":null,"cost_usd":null,"metrics_source":"unavailable","result":"completed"}
```

If information arrives as a cumulative session total, store it separately; do not add that total to already counted tasks. Mark which stages it covers: research, translation, editing, checks, and retries. Do not present a partial journal as complete billing. `null` means unknown, not zero. Cache is already included in input tokens where the provider reports it that way; do not count it twice. Account percentages and API dollars are different measures.

## Memory Without Context Growth

The lead holds the shared decision document and glossary. The worker receives a short extract. A summary conveys the course of the argument, pronoun referents, accepted meanings, and unresolved references; it does not replace the source text. Do not discard contextual distinctions for a fixed length. Check the summary against the accepted translation before using it in later assignments.
