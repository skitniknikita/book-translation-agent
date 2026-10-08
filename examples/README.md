# Try the workflow with a short original text

[sample-source.md](sample-source.md) was written for this repository. It is a
synthetic essay, not an extract from a published book. It contains headings,
conceptual distinctions, a quotation, a list, and a footnote.

Open this repository in Codex and ask:

```text
Use $translate-book on examples/sample-source.md. Translate into Russian and
save everything under books/sample-output. Keep the sample source unchanged.
Research the key terms online before translating. Do not invent published
translations of this fictional essay. Use the configured large-lead/small-worker
workflow, save progress, and produce the glossary, translation, and checked EPUB.
```

This starts actual model work and uses your Codex allowance. For a local check
without model calls, use `python3 launch.py --check` or run the test suite.

The example intentionally does not include a fabricated approved glossary,
model-selection record, or completed review receipts. The agent must create real
evidence during the run. It extracts the source blocks using the documented
[automation procedure](../.agents/skills/translate-book/references/automation.md).

Check that the distinction between attention and care, the cautious wording,
the quotation, and the footnote survive. Automated checks alone cannot establish
that the translation preserves those meanings.
