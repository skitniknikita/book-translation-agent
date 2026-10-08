"""Tests for selection validation and catalog pagination, entirely offline."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import os
import stat
import tempfile
import time
import unittest

import model_selection as models


def page(model_id, effort, cursor=None):
    result = {"data": [{"id": model_id, "model": "route-" + model_id,
                        "supportedReasoningEfforts": [{"reasoningEffort": effort}]}],
              "nextCursor": cursor}
    return result


class ModelSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.book = Path(self.temp.name) / "source.md"
        self.book.write_text("source", encoding="utf-8")
        self.catalog = models.merge_catalog_pages([
            page("new-large-id", "high", "second"),
            page("new-small-id", "medium", None),
        ])

    def tearDown(self):
        self.temp.cleanup()

    def selection(self):
        evidence = lambda role: {"role": role, "basis": "reviewed criteria",
                                 "evidence": [{"kind": "assessment", "source": "https://openai.com/models",
                                               "summary": "recorded assessment"}]}
        source_hash = models.sha256_file(self.book)
        return {"schema_version": 1, "selected_at": datetime.now(timezone.utc).isoformat(),
                "source": {"path": str(self.book), "sha256": source_hash},
                "source_sha256": source_hash, "catalog": self.catalog,
                "catalog_sha256": models.catalog_sha256(self.catalog),
                "leader": {"model": "route-new-large-id", "reasoning_effort": "high", "classification": evidence("leader")},
                "worker": {"model": "route-new-small-id", "reasoning_effort": "medium", "classification": evidence("worker")},
                "sources": [{"url": models.OFFICIAL_MODEL_LIST_DOCS, "accessed_at": "2026-10-08"}],
                "rationale": "quality first", "account_access": "not_verified_by_catalog"}

    def test_unknown_future_ids_are_accepted_when_evidence_is_explicit(self):
        selection = self.selection()
        self.assertEqual(models.validate_selection(selection, self.book, require_fresh=True), selection)

    def test_stale_selection_rejected_only_for_a_new_book(self):
        selection = self.selection()
        selection["selected_at"] = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        with self.assertRaisesRegex(models.ModelSelectionError, "не старше"):
            models.validate_selection(selection, self.book, require_fresh=True)
        self.assertEqual(models.validate_selection(selection, self.book, require_fresh=False), selection)

    def test_old_or_future_catalog_is_rejected_for_new_book(self):
        selection = self.selection()
        selection["catalog"]["collected_at"] = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        selection["catalog_sha256"] = models.catalog_sha256(selection["catalog"])
        with self.assertRaisesRegex(models.ModelSelectionError, "catalog.collected_at"):
            models.validate_selection(selection, self.book, require_fresh=True)
        selection = self.selection()
        selection["selected_at"] = (datetime.now(timezone.utc) + timedelta(minutes=6)).isoformat()
        with self.assertRaisesRegex(models.ModelSelectionError, "будущем"):
            models.validate_selection(selection, self.book, require_fresh=False)

    def test_mismatched_source_and_unsupported_effort_are_rejected(self):
        selection = self.selection()
        selection["source_sha256"] = "changed"
        with self.assertRaisesRegex(models.ModelSelectionError, "Хеш исходника"):
            models.validate_selection(selection, self.book, require_fresh=True)
        selection = self.selection()
        selection["worker"]["reasoning_effort"] = "max"
        with self.assertRaisesRegex(models.ModelSelectionError, "не поддерживается"):
            models.validate_selection(selection, self.book, require_fresh=True)

    def test_explicit_role_evidence_is_required(self):
        selection = self.selection()
        del selection["leader"]["classification"]["evidence"]
        with self.assertRaisesRegex(models.ModelSelectionError, "свидетельства"):
            models.validate_selection(selection, self.book, require_fresh=True)

    def test_source_path_is_provenance_but_hash_keeps_copied_book_valid(self):
        selection = self.selection()
        selection["source"]["path"] = "/another-machine/source.md"
        self.assertEqual(models.validate_selection(selection, self.book, require_fresh=True), selection)

    def test_hidden_model_and_nonofficial_role_evidence_rejected(self):
        selection = self.selection()
        selection["catalog"]["models"][1]["hidden"] = True
        selection["catalog_sha256"] = models.catalog_sha256(selection["catalog"])
        with self.assertRaisesRegex(models.ModelSelectionError, "отсутствует"):
            models.validate_selection(selection, self.book, require_fresh=True)
        selection = self.selection()
        selection["leader"]["classification"]["evidence"][0]["source"] = "https://example.org/models"
        with self.assertRaisesRegex(models.ModelSelectionError, "официальную"):
            models.validate_selection(selection, self.book, require_fresh=True)

    def test_incomplete_duplicate_and_bad_paginated_catalog_rejected(self):
        with self.assertRaisesRegex(models.ModelSelectionError, "Не все страницы"):
            models.merge_catalog_pages([page("a", "high", "still-more")])
        with self.assertRaisesRegex(models.ModelSelectionError, "повторяется"):
            models.merge_catalog_pages([page("a", "high", "second"), page("a", "medium")])
        with self.assertRaisesRegex(models.ModelSelectionError, "порядке cursor"):
            models.merge_catalog_pages([page("a", "high", "second"), {**page("b", "medium"), "requestCursor": "wrong"}])

    def test_offline_pages_fixture_is_complete_and_readable(self):
        path = Path(self.temp.name) / "pages.json"
        path.write_text(json.dumps({"pages": [page("a", "high", "second"), page("b", "medium")]}), encoding="utf-8")
        catalog = models.load_catalog(path)
        self.assertTrue(catalog["complete"])
        self.assertEqual([item["id"] for item in catalog["models"]], ["a", "b"])

    def test_app_server_jsonl_paginates_without_inference(self):
        fake = Path(self.temp.name) / "fake-codex"
        fake.write_text("""#!/usr/bin/env python3
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    if request.get('method') == 'initialize':
        print(json.dumps({'id': request['id'], 'result': {}}), flush=True)
    elif request.get('method') == 'model/list':
        cursor = request['params'].get('cursor')
        data = {'data': [{'id': 'opaque-' + str(cursor or 'first'), 'model': 'route-' + str(cursor or 'first'), 'supportedReasoningEfforts': [{'reasoningEffort': 'high'}]}], 'nextCursor': 'next' if cursor is None else None}
        print(json.dumps({'id': request['id'], 'result': data}), flush=True)
""", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        catalog = models.query_catalog(str(fake), timeout=3)
        self.assertEqual([item['model'] for item in catalog['models']], ['route-first', 'route-next'])

    def test_app_server_timeout_is_bounded_and_reaped(self):
        fake = Path(self.temp.name) / "hanging-codex"
        fake.write_text("""#!/usr/bin/env python3
import time
time.sleep(10)
""", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        started = time.monotonic()
        with self.assertRaisesRegex(models.ModelSelectionError, "Истекло"):
            models.query_catalog(str(fake), timeout=0.1)
        self.assertLess(time.monotonic() - started, 2.5)


if __name__ == "__main__":
    unittest.main()
