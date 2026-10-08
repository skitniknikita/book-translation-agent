"""Workflow gates are bookkeeping tests, not claims about model quality."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/translate-book/scripts/book_workflow.py"
if str(SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT.parent))
import book_model_selection as book_models
spec = importlib.util.spec_from_file_location("book_workflow", SCRIPT)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


class BookWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Author — Test Book"
        self.root.mkdir()
        self.source = self.root / "source.md"
        self.source_bytes = b"# Original\n\nA source the workflow must never rewrite.\n"
        self.source.write_bytes(self.source_bytes)

    def tearDown(self):
        self.temp.cleanup()

    def blocks(self, dependent=False):
        blocks = [
            {"id": "h1", "kind": "heading", "section": "I", "complexity": "normal",
             "text": "I. First section", "term_ids": []},
            {"id": "p1", "kind": "paragraph", "section": "I", "complexity": "normal",
             "text": "A threshold appears here[^n1].", "term_ids": ["threshold"]},
            {"id": "n1", "kind": "footnote", "section": "I", "complexity": "normal",
             "text": "[^n1]: The note must keep its exact label.", "term_ids": []},
        ]
        if dependent:
            blocks.extend([
                {"id": "p2", "kind": "paragraph", "section": "I", "complexity": "normal",
                 "break_before": True, "text": "The argument continues.", "term_ids": []},
                {"id": "h2", "kind": "heading", "section": "II", "complexity": "normal",
                 "text": "II. Separate section", "term_ids": []},
            ])
        return blocks

    def selection(self):
        catalog = book_models.merge_catalog_pages([
            {"data": [{"id": "leader", "model": "leader-model",
                       "supportedReasoningEfforts": [{"reasoningEffort": "high"}]}],
             "nextCursor": "worker"},
            {"requestCursor": "worker", "data": [{"id": "worker", "model": "worker-model",
                       "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}],
             "nextCursor": None},
        ])
        def classification(role):
            return {"role": role, "basis": "Synthetic routing evidence.",
                    "evidence": [{"kind": "assessment", "source": "https://openai.com/models/" + role,
                                  "summary": "Test-only selection evidence."}]}
        source_hash = sha256(self.source_bytes)
        return {
            "schema_version": 1, "selected_at": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(self.source), "sha256": source_hash}, "source_sha256": source_hash,
            "catalog": catalog, "catalog_sha256": book_models.catalog_sha256(catalog),
            "leader": {"model": "leader-model", "reasoning_effort": "high", "classification": classification("leader")},
            "worker": {"model": "worker-model", "reasoning_effort": "medium", "classification": classification("worker")},
            "sources": [{"url": book_models.OFFICIAL_MODEL_LIST_DOCS, "accessed_at": "2026-10-08"}],
            "rationale": "Synthetic test routing.", "account_access": "not_verified_by_catalog",
        }

    def create(self, blocks=None):
        return workflow.Book.initialize(self.root, self.source, blocks or self.blocks(), self.selection())

    def write(self, relative, text="evidence\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return relative

    def terms(self, target="порог"):
        return [{
            "id": "threshold", "source": "threshold", "sense": "conceptual limit",
            "target": target, "status": "working", "confidence": "medium",
            "rationale": "Fixture decision only.", "search_log": "No published equivalent found.",
        }]

    def approve_glossary(self, book, target="порог", index_complete=True, global_rules=None):
        self.write("00_Глоссарий.md", "# Glossary\n\nthreshold — " + target + "\n")
        report = self.write("work/evidence/glossary.txt")
        book.approve_glossary(self.terms(target), [b["id"] for b in book.blocks], report,
                              index_complete, global_rules)

    def calibration_record(self, book, root=None):
        root = root or self.root
        def write(relative, text="evidence\n"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return relative
        report = write("work/evidence/calibration.txt")
        model_evidence = write("work/evidence/calibration-model.txt")
        cases = []
        for kind, block_id in (("ordinary", book.blocks[0]["id"]), ("difficult", book.blocks[1]["id"])):
            draft = "work/trials/%s.json" % kind
            write(draft, json.dumps({"blocks": [{"id": block_id, "text": "Trial " + kind}]}, ensure_ascii=False))
            worker_evidence = write("work/evidence/%s-worker.txt" % kind)
            cases.append({"kind": kind, "source_ids": [block_id],
                          "source_sha256": workflow.digest([book.by_id[block_id]]), "draft": draft,
                          "worker_evidence": worker_evidence})
        return {"passed": True, "cases": cases, "observed_model": "leader-model",
                "observed_worker_model": "worker-model", "report": report,
                "model_evidence": model_evidence}

    def calibrate(self, book, root=None):
        record = self.calibration_record(book, root)
        book.calibrate(record)
        return record

    def draft(self, book, ident):
        packet = book.packet(ident, "draft")
        chunk = book.chunk(ident)
        translated = []
        for block_id in chunk["block_ids"]:
            source = book.by_id[block_id]["text"]
            translated.append({"id": block_id, "text": "RU: " + source})
        book.submit(ident, {"packet_sha256": packet["sha256"], "blocks": translated})

    def review(self, book, ident, stage):
        packet = book.packet(ident, stage)
        report = self.write("work/evidence/%s-%s-report.txt" % (ident, stage))
        model_evidence = self.write("work/evidence/%s-%s-model.txt" % (ident, stage))
        book.record_review(ident, {
            "stage": stage, "packet_sha256": packet["sha256"],
            "reviewed_ids": book.chunk(ident)["block_ids"], "issues": [],
            "observed_model": "leader-model" if stage in {"meaning", "terminology"} else "worker-model",
            "report": report, "model_evidence": model_evidence,
        })

    def accept(self, book, ident, summary=True):
        self.draft(book, ident)
        for stage in workflow.STAGES:
            self.review(book, ident, stage)
        if summary:
            report = self.write("work/evidence/%s-summary.txt" % ident)
            book.record_summary(ident, {"observed_model": "leader-model", "text": "Prior context.",
                                        "report": report})

    def test_init_preserves_original_source_and_never_overwrites_work(self):
        book = self.create()
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual((self.root / "work/source-original.md").read_bytes(), self.source_bytes)
        with self.assertRaisesRegex(ValueError, "уже создана"):
            workflow.Book.initialize(self.root, self.source, self.blocks(), self.selection())
        self.assertEqual(book.state["source"]["sha256"], sha256(self.source_bytes))

    def test_model_selection_file_cannot_be_silently_rebound_after_init(self):
        book = self.create()
        self.approve_glossary(book)
        book.plan()
        selection = json.loads((self.root / "work/model-selection.json").read_text(encoding="utf-8"))
        selection["source_sha256"] = "0" * 64
        (self.root / "work/model-selection.json").write_text(json.dumps(selection), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "изменён"):
            book.packet("part-0001", "draft")

    def test_glossary_requires_full_coverage_and_opened_source_evidence(self):
        book = self.create()
        self.write("00_Глоссарий.md", "# Glossary\n")
        evidence = self.write("work/evidence/glossary.txt")
        with self.assertRaisesRegex(ValueError, "покрывать все"):
            book.approve_glossary(self.terms(), ["h1", "p1"], evidence)
        sourced = copy.deepcopy(self.terms())
        sourced[0].pop("search_log")
        sourced[0]["status"] = "established"
        sourced[0]["sources"] = [{"url": "https://example.test/term", "title": "Source",
                                    "accessed_at": "2026-10-08", "locator": "", "evidence": "opened"}]
        with self.assertRaisesRegex(ValueError, "открыт/не описан"):
            book.approve_glossary(sourced, [b["id"] for b in book.blocks], evidence)
        sourced[0]["sources"][0]["locator"] = "p. 1"
        sourced[0]["sources"][0]["evidence"] = ""
        with self.assertRaisesRegex(ValueError, "открыт/не описан"):
            book.approve_glossary(sourced, [b["id"] for b in book.blocks], evidence)

    def test_plan_preserves_all_blocks_sections_and_only_expands_simple_after_calibration(self):
        simple = [
            {"id": "a", "kind": "paragraph", "section": "One", "complexity": "simple", "text": "a " * 700, "term_ids": []},
            {"id": "b", "kind": "paragraph", "section": "One", "complexity": "simple", "text": "b " * 700, "term_ids": []},
            {"id": "c", "kind": "paragraph", "section": "Two", "complexity": "simple", "text": "c " * 10, "term_ids": []},
        ]
        uncalibrated_root = self.root / "uncalibrated"
        uncalibrated_root.mkdir()
        source = uncalibrated_root / "source.txt"
        source.write_bytes(self.source_bytes)
        selection = self.selection()
        uncalibrated = workflow.Book.initialize(uncalibrated_root, source, simple, selection)
        (uncalibrated_root / "00_Глоссарий.md").write_text("# G\n")
        (uncalibrated_root / "work/evidence").mkdir(parents=True)
        (uncalibrated_root / "work/evidence/g.txt").write_text("proof\n")
        uncalibrated.approve_glossary([], ["a", "b", "c"], "work/evidence/g.txt")
        before = uncalibrated.plan()
        self.assertEqual([c["block_ids"] for c in before], [["a"], ["b"], ["c"]])

        calibrated_root = self.root / "calibrated"
        calibrated_root.mkdir()
        calibrated_source = calibrated_root / "source.txt"
        calibrated_source.write_bytes(self.source_bytes)
        calibrated = workflow.Book.initialize(calibrated_root, calibrated_source, simple, selection)
        (calibrated_root / "00_Глоссарий.md").write_text("# G\n")
        (calibrated_root / "work/evidence").mkdir(parents=True)
        (calibrated_root / "work/evidence/g.txt").write_text("proof\n")
        calibrated.approve_glossary([], ["a", "b", "c"], "work/evidence/g.txt")
        self.calibrate(calibrated, calibrated_root)
        after = calibrated.plan()
        self.assertEqual([c["block_ids"] for c in after], [["a", "b"], ["c"]])
        self.assertEqual([block for chunk in after for block in chunk["block_ids"]], ["a", "b", "c"])
        self.assertEqual([chunk["section"] for chunk in after], ["One", "Two"])

    def test_language_packet_is_compact_and_does_not_send_original_text(self):
        book = self.create()
        self.approve_glossary(book)
        book.plan()
        self.draft(book, "part-0001")
        packet = book.packet("part-0001", "language")
        data = json.loads(Path(packet["path"]).read_text(encoding="utf-8"))
        self.assertEqual(set(data["blocks"][0]), {"id", "kind", "text"})
        self.assertTrue(all(item["text"].startswith("RU: ") for item in data["blocks"]))
        self.assertNotIn(book.by_id["p1"]["text"], [item["text"] for item in data["blocks"]])
        self.assertNotIn("translation", data)

    def test_submit_demands_exact_ids_and_footnote_labels(self):
        book = self.create()
        self.approve_glossary(book)
        book.plan()
        packet = book.packet("part-0001", "draft")
        chunk = book.chunk("part-0001")
        valid = [{"id": i, "text": "RU: " + book.by_id[i]["text"]} for i in chunk["block_ids"]]
        with self.assertRaisesRegex(ValueError, "Пропущены"):
            book.submit("part-0001", {"packet_sha256": packet["sha256"], "blocks": valid[:-1]})
        bad_notes = copy.deepcopy(valid)
        bad_notes[1]["text"] = bad_notes[1]["text"].replace("[^n1]", "[^wrong]")
        with self.assertRaisesRegex(ValueError, "снос"):
            book.submit("part-0001", {"packet_sha256": packet["sha256"], "blocks": bad_notes})
        book.submit("part-0001", {"packet_sha256": packet["sha256"], "blocks": valid})

    def test_patch_is_optimistic_and_atomic_on_old_text_mismatch(self):
        book = self.create()
        self.approve_glossary(book)
        book.plan()
        self.draft(book, "part-0001")
        packet = book.packet("part-0001", "language")
        original = copy.deepcopy(book.chunk("part-0001")["translations"])
        ids = book.chunk("part-0001")["block_ids"]
        result = {"packet_sha256": packet["sha256"], "changes": [
            {"id": ids[0], "old": original[ids[0]], "new": "Edited heading"},
            {"id": ids[1], "old": "obsolete text", "new": "Edited paragraph[^n1]"},
        ]}
        with self.assertRaisesRegex(ValueError, "не совпадает"):
            book.apply_changes("part-0001", "language", result)
        self.assertEqual(book.chunk("part-0001")["translations"], original)

    def test_reviews_bind_translation_glossary_model_and_evidence_files(self):
        book = self.create()
        self.approve_glossary(book)
        self.calibrate(book)
        book.plan()
        self.accept(book, "part-0001")
        chunk = book.chunk("part-0001")
        self.assertTrue(book.ready(chunk))
        patch = book.packet("part-0001", "language")
        block_id = chunk["block_ids"][0]
        book.apply_changes("part-0001", "language", {"packet_sha256": patch["sha256"], "changes": [{
            "id": block_id, "old": chunk["translations"][block_id], "new": "Edited heading"
        }]})
        self.assertFalse(book.review_current(chunk, "language"))
        # Restore a full accepted state before independently testing file and model receipts.
        self.review(book, "part-0001", "language")
        report = self.root / chunk["reviews"]["language"]["report"]["path"]
        report.write_text("changed\n")
        self.assertFalse(book.review_current(chunk, "language"))
        report.write_text("evidence\n")
        self.review(book, "part-0001", "language")
        model_proof = self.root / chunk["reviews"]["language"]["model_evidence"]["path"]
        model_proof.write_text("changed model proof\n")
        self.assertFalse(book.review_current(chunk, "language"))
        model_proof.write_text("evidence\n")
        self.review(book, "part-0001", "language")
        selection_path = self.root / "work/model-selection.json"
        changed_selection = json.loads(selection_path.read_text())
        changed_selection["audit_note"] = "selection changed"
        selection_path.write_text(json.dumps(changed_selection), encoding="utf-8")
        self.assertFalse(book.review_current(chunk, "language"))

    def test_selection_file_is_pinned_and_reselection_is_explicit_and_invalidates_calibration(self):
        book = self.create()
        self.approve_glossary(book)
        self.calibrate(book)
        selection_path = self.root / "work/model-selection.json"
        edited = json.loads(selection_path.read_text(encoding="utf-8"))
        edited["rationale"] = "Silent edit must not be accepted."
        selection_path.write_text(json.dumps(edited), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "изменён"):
            book.models()
        replacement = self.selection()
        replacement["rationale"] = "Explicit replacement with a recorded reason."
        book.reselect(replacement, "Updated model evaluation.")
        self.assertEqual(book.models()["leader"]["model"], "leader-model")
        self.assertIsNone(book.state["calibration"])
        self.assertEqual(book.state["review_order"], "meaning-first")
        self.assertTrue(any((self.root / "work/model-history").iterdir()))

    def test_calibration_rejects_mismatched_trial_and_changed_trial_evidence_becomes_stale(self):
        book = self.create()
        self.approve_glossary(book)
        record = self.calibration_record(book)
        record["cases"][0]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "другому исходному"):
            book.calibrate(record)
        record = self.calibrate(book)
        self.assertTrue(book.calibration_current())
        trial_path = self.root / record["cases"][0]["draft"]
        trial_path.write_text(json.dumps({"blocks": [{"id": "h1", "text": "changed"}]}), encoding="utf-8")
        self.assertFalse(book.calibration_current())

    def test_glossary_change_stales_only_linked_chunks_and_dependent_context(self):
        book = self.create(self.blocks(dependent=True))
        shared_rules = "Shared style and distinctions."
        self.approve_glossary(book, "порог", global_rules=shared_rules)
        self.calibrate(book)
        book.plan()
        self.accept(book, "part-0001")
        self.accept(book, "part-0002")
        self.accept(book, "part-0003")
        one, two, three = (book.chunk("part-0001"), book.chunk("part-0002"), book.chunk("part-0003"))
        self.assertTrue(all(book.review_current(c, "language") for c in (one, two, three)))
        self.approve_glossary(book, "рубеж", global_rules=shared_rules)
        self.assertFalse(book.review_current(one, "language"))
        self.assertFalse(book.review_current(two, "language"))
        self.assertTrue(book.review_current(three, "language"))

    def test_dependent_draft_requires_accepted_summary_and_calibration_after_first_two(self):
        blocks = self.blocks(dependent=True) + [
            {"id": "p3", "kind": "paragraph", "section": "III", "complexity": "normal",
             "text": "A third independent part.", "term_ids": []},
        ]
        book = self.create(blocks)
        self.approve_glossary(book)
        book.plan()
        with self.assertRaisesRegex(ValueError, "предыдущий"):
            book.packet("part-0002", "draft")
        self.accept(book, "part-0001", summary=False)
        with self.assertRaisesRegex(ValueError, "предыдущий"):
            book.packet("part-0002", "draft")
        report = self.write("work/evidence/part-0001-summary.txt")
        book.record_summary("part-0001", {"observed_model": "leader-model", "text": "Context.", "report": report})
        self.assertIsInstance(book.packet("part-0002", "draft"), dict)
        self.accept(book, "part-0002")
        with self.assertRaisesRegex(ValueError, "калибровка"):
            book.packet("part-0003", "draft")
        self.calibrate(book)
        self.assertIsInstance(book.packet("part-0003", "draft"), dict)

    def test_status_resumes_from_saved_state_and_duplicate_usage_is_not_double_counted(self):
        book = self.create()
        self.approve_glossary(book)
        book.plan()
        resumed = workflow.Book(self.root)
        self.assertEqual(resumed.status()["chunks"][0]["next"], "draft")
        record = {"task_id": "task-1", "scope": "task_delta", "input_tokens": 11,
                  "cached_input_tokens": 3, "output_tokens": 5}
        self.assertTrue(resumed.usage(record))
        self.assertFalse(resumed.usage(copy.deepcopy(record)))
        rows = [json.loads(line) for line in (self.root / "work/usage.jsonl").read_text().splitlines()]
        self.assertEqual(rows, [record])
        conflict = dict(record, output_tokens=6)
        with self.assertRaisesRegex(ValueError, "Повторный task_id"):
            resumed.usage(conflict)

    def test_bank_keeps_author_scoped_context_variants(self):
        bank = self.root / "term-bank.json"
        first = {"id": "threshold", "source": "threshold", "sense": "political", "target": "порог"}
        second = {"id": "threshold", "source": "threshold", "sense": "temporal", "target": "рубеж"}
        self.assertEqual(workflow.bank_merge(bank, "Author", [first, second]), 2)
        self.assertEqual(workflow.bank_merge(bank, "Author", [first]), 2)
        with self.assertRaisesRegex(ValueError, "другому автору"):
            workflow.bank_merge(bank, "Other", [first])

    def test_assemble_waits_for_every_review_and_preserves_block_order_and_notes(self):
        book = self.create()
        self.approve_glossary(book)
        self.calibrate(book)
        book.plan()
        self.draft(book, "part-0001")
        with self.assertRaisesRegex(ValueError, "проверки"):
            book.assemble()
        for stage in workflow.STAGES:
            self.review(book, "part-0001", stage)
        text, anchors = book.assemble()
        rendered = text.read_text(encoding="utf-8")
        self.assertEqual(anchors, ["bt-h1", "bt-p1"])
        self.assertLess(rendered.index("RU: I. First section"), rendered.index("RU: A threshold appears here[^n1]."))
        self.assertLess(rendered.index("RU: A threshold appears here[^n1]."), rendered.index("RU: [^n1]: The note"))
        external = rendered + "\nВнешняя ручная правка.\n"
        text.write_text(external, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "внешние правки"):
            book.assemble()
        self.assertEqual(text.read_text(encoding="utf-8"), external)

    def test_preparation_files_allow_init_without_replacing_model_selection(self):
        work = self.root / "work"
        work.mkdir()
        selection_path = work / "model-selection.json"
        selection = self.selection()
        selection_path.write_text(json.dumps(selection, ensure_ascii=False), encoding="utf-8")
        catalog_path = work / "model-catalog.json"
        catalog_path.write_text('{"items": ["preparation evidence"]}\n', encoding="utf-8")
        selection_before = selection_path.stat()
        catalog_before = catalog_path.stat()
        book = workflow.Book.initialize(self.root, self.source, self.blocks(), selection)
        self.assertEqual(book.models(), selection)
        self.assertEqual(selection_path.stat().st_ino, selection_before.st_ino)
        self.assertEqual(selection_path.read_text(encoding="utf-8"), json.dumps(selection, ensure_ascii=False))
        self.assertEqual(catalog_path.stat().st_ino, catalog_before.st_ino)
        self.assertTrue(catalog_path.is_file())

    def test_init_rejects_prepared_selection_for_a_different_source_before_writing_state(self):
        book_root = self.root / "wrong-preparation"
        book_root.mkdir()
        source = book_root / "source.md"
        source.write_bytes(self.source_bytes)
        work = book_root / "work"
        work.mkdir()
        wrong = self.selection()
        wrong["source_sha256"] = "0" * 64
        (work / "model-selection.json").write_text(json.dumps(wrong), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "другому исходнику"):
            workflow.Book.initialize(book_root, source, self.blocks())
        self.assertFalse((work / "state.json").exists())

    def test_meaning_first_is_default_and_language_first_requires_complete_comparison_evidence(self):
        with self.assertRaisesRegex(ValueError, "compare-order"):
            workflow.Book.initialize(self.root, self.source, self.blocks(), self.selection(), "language-first")
        book = self.create()
        self.assertEqual(book.state["review_order"], "meaning-first")
        first_blocks = [block for block in book.blocks if block["section"] == "I"]
        source_sha = workflow.digest(first_blocks)
        def comparison_trial(order, path):
            self.write(path, json.dumps({"source_sha256": source_sha, "review_order": order,
                                         "blocks": [{"id": block["id"], "text": "Trial " + block["id"]}
                                                    for block in first_blocks]}, ensure_ascii=False))
            return path
        baseline = comparison_trial("meaning-first", "work/evidence/baseline.json")
        candidate = comparison_trial("language-first", "work/evidence/candidate.json")
        incomplete = {"chapter_id": "I", "source_sha256": source_sha, "accepted": True,
                      "observed_model": "leader-model", "baseline_report": baseline,
                      "candidate_report": candidate}
        with self.assertRaises((ValueError, KeyError)):
            book.compare_order(incomplete)
        self.assertEqual(book.state["review_order"], "meaning-first")
        assessment = self.write("work/evidence/assessment.txt", "comparison assessment\n")
        book.compare_order({**incomplete, "assessment": assessment})
        self.assertEqual(book.state["review_order"], "language-first")
        self.write(candidate, "changed comparison evidence\n")
        self.assertEqual(book.effective_order(), "meaning-first")

    def test_comparison_of_other_chapter_cannot_change_order_after_later_translation_starts(self):
        book = self.create(self.blocks(dependent=True))
        self.approve_glossary(book)
        self.calibrate(book)
        book.plan()
        book.chunk("part-0003")["translations"] = {"h2": "Уже начат второй раздел."}
        first_blocks = [block for block in book.blocks if block["section"] == "I"]
        source_sha = workflow.digest(first_blocks)
        for order, path in (("meaning-first", "work/evidence/base.json"),
                            ("language-first", "work/evidence/candidate.json")):
            self.write(path, json.dumps({"source_sha256": source_sha, "review_order": order,
                                         "blocks": [{"id": b["id"], "text": "trial"} for b in first_blocks]}))
        assessment = self.write("work/evidence/assessment.txt")
        with self.assertRaisesRegex(ValueError, "последующих разделов"):
            book.compare_order({"chapter_id": "I", "source_sha256": source_sha, "accepted": True,
                                "observed_model": "leader-model", "baseline_report": "work/evidence/base.json",
                                "candidate_report": "work/evidence/candidate.json", "assessment": assessment})

    def test_cli_new_book_happy_path_init_glossary_plan_and_status(self):
        blocks_path = self.root / "blocks.json"
        blocks_path.write_text(json.dumps(self.blocks(), ensure_ascii=False), encoding="utf-8")
        selection_path = self.root / "selection.json"
        selection_path.write_text(json.dumps(self.selection(), ensure_ascii=False), encoding="utf-8")
        def command(*args):
            return subprocess.run([sys.executable, str(SCRIPT), "--book-dir", str(self.root), *args],
                                  cwd=self.root, text=True, capture_output=True, check=False)

        init = command("init", "--source", str(self.source), "--blocks", str(blocks_path),
                       "--selection", str(selection_path))
        self.assertEqual(init.returncode, 0, init.stderr)
        self.write("00_Глоссарий.md", "# Глоссарий\n\nthreshold — порог\n")
        self.write("work/evidence/glossary.txt", "opened sources and coverage\n")
        record = {
            "terms": self.terms(), "reviewed_ids": [b["id"] for b in self.blocks()],
            "report": "work/evidence/glossary.txt", "index_complete": True,
            "global_rules": "Synthetic shared rule.",
        }
        record_path = self.root / "glossary-record.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        glossary = command("glossary", "--record", str(record_path))
        self.assertEqual(glossary.returncode, 0, glossary.stderr)
        plan = command("plan")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertEqual(json.loads(plan.stdout)[0]["block_ids"], ["h1", "p1", "n1"])
        status = command("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["chunks"][0]["next"], "draft")

    def test_build_epub_tracks_metadata_css_and_assets_and_preserves_previous_file_on_failure(self):
        blocks = [
            {"id": "h1", "kind": "heading", "section": "One", "complexity": "normal",
             "text": "# Глава первая", "term_ids": []},
            {"id": "p1", "kind": "paragraph", "section": "One", "complexity": "normal",
             "text": "Первый абзац с примечанием.[^note]", "term_ids": ["threshold"]},
            {"id": "note", "kind": "footnote", "section": "One", "complexity": "normal",
             "text": "[^note]: Первая строка примечания.\n\n    Вторая строка того же примечания.", "term_ids": []},
            {"id": "h2", "kind": "heading", "section": "Two", "complexity": "normal",
             "text": "# Глава вторая", "term_ids": []},
            {"id": "p2", "kind": "paragraph", "section": "Two", "complexity": "normal",
             "text": "Второй абзац с локальной схемой.\n\n![Схема](assets/pixel.png)", "term_ids": []},
        ]
        book = self.create(blocks)
        self.approve_glossary(book, global_rules="Synthetic shared policy.")
        self.calibrate(book)
        book.plan()
        self.assertEqual([c["block_ids"] for c in book.state["chunks"]],
                         [["h1", "p1", "note"], ["h2", "p2"]])
        self.accept(book, "part-0001")
        self.accept(book, "part-0002")
        metadata = {
            "title": "Синтетическая книга", "creator": "Тестовый автор", "language": "ru",
            "rights": "Только для тестирования.", "source": "Синтетический источник.",
            "unofficial_note": "Неофициальный рабочий перевод.",
        }
        self.write("metadata.json", json.dumps(metadata, ensure_ascii=False))
        self.write("epub.css", "body { color: #222; }\n")
        pixel = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
            "0WJg3gAAAABJRU5ErkJggg=="
        )
        asset = self.root / "assets/pixel.png"
        asset.parent.mkdir()
        asset.write_bytes(pixel)
        result = book.build("Author — Test Book.epub", "metadata.json", "epub.css")
        output = self.root / "Author — Test Book.epub"
        self.assertTrue(output.is_file())
        self.assertTrue(result["reverse_text_checked"])
        self.assertTrue(book.status()["epub_current"])
        previous = output.read_bytes()

        metadata["title"] = "Синтетическая книга, исправленное издание"
        self.write("metadata.json", json.dumps(metadata, ensure_ascii=False))
        self.assertFalse(book.status()["epub_current"])
        metadata["rights"] = ""
        self.write("metadata.json", json.dumps(metadata, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, "rights"):
            book.build("Author — Test Book.epub", "metadata.json", "epub.css")
        self.assertEqual(output.read_bytes(), previous)

        metadata["rights"] = "Только для тестирования."
        self.write("metadata.json", json.dumps(metadata, ensure_ascii=False))
        asset.unlink()
        self.assertFalse(book.status()["epub_current"])
        with self.assertRaisesRegex(ValueError, "не найден"):
            book.build("Author — Test Book.epub", "metadata.json", "epub.css")
        self.assertEqual(output.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
