"""Offline tests for the launcher; they never ask a model to infer."""
import importlib.util
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("launch", ROOT / "launch.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Книги с пробелами"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns("__pycache__", "._*"))
        self.book = self.root / "Исходник.md"
        self.book.write_text("A short source.", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def selection(self):
        from model_selection import catalog_sha256, sha256_file
        catalog = {"schema_version": 1, "collected_at": datetime.now(timezone.utc).isoformat(),
                   "complete": True, "source": {"kind": "fixture"}, "models": [
            {"id": "future-leader-42", "supportedReasoningEfforts": [{"reasoningEffort": "high"}]},
            {"id": "future-worker-99", "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]},
        ]}
        evidence = lambda role: {"role": role, "basis": "reviewed current catalog and task needs",
                                 "evidence": [{"kind": "review", "source": "https://openai.com/models",
                                               "summary": "explicit human/model judgment"}]}
        source_hash = sha256_file(self.book)
        return {"schema_version": 1, "selected_at": datetime.now(timezone.utc).isoformat(),
                "source": {"path": str(self.book), "sha256": source_hash},
                "source_sha256": source_hash, "catalog": catalog,
                "catalog_sha256": catalog_sha256(catalog), "leader": {
                    "model": "future-leader-42", "reasoning_effort": "high", "classification": evidence("leader")},
                "worker": {"model": "future-worker-99", "reasoning_effort": "medium", "classification": evidence("worker")},
                "sources": [{"url": "https://learn.chatgpt.com/docs/app-server#models", "accessed_at": "2026-10-08"}],
                "rationale": "quality first, a separate economical worker", "account_access": "not_verified_by_catalog"}

    def write_selection(self):
        path = launch.resolve_book_dir(self.root, self.book, None) / "work/model-selection.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(self.selection()), encoding="utf-8")
        return path

    def test_selected_unknown_future_models_are_explicitly_routed(self):
        selection = self.selection()
        book_dir = launch.resolve_book_dir(self.root, self.book, None)
        command = launch.build_command(self.root, launch.validate_package(self.root), "codex", self.book, book_dir,
                                       book_dir / "work/model-selection.json", selection)
        self.assertEqual(command[command.index("-m") + 1], "future-leader-42")
        self.assertIn('agents.default_subagent_model="future-worker-99"', command)
        self.assertIn('agents.default_subagent_reasoning_effort="medium"', command)
        self.assertNotIn("gpt-5.6-terra", command)
        self.assertEqual(command[command.index("-s") + 1], "workspace-write")

    def test_role_model_drift_rejected(self):
        role = self.root / ".codex/agents/book-translator.toml"
        role.write_text(role.read_text(encoding="utf-8") + '\nmodel = "fixed"\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "selection"):
            launch.validate_package(self.root)

    def test_literal_book_path(self):
        name = 'Книга $(echo injected) `test`.md'
        book = self.root / name
        book.write_text("A short source.", encoding="utf-8")
        book_dir = launch.resolve_book_dir(self.root, book, None)
        command = launch.build_command(self.root, launch.validate_package(self.root), "codex", book, book_dir,
                                       book_dir / "work/model-selection.json",
                                       self.selection() | {"source": {"path": str(book), "sha256": "x"}})
        self.assertIn(name, command[-1])
        self.assertEqual(command.count(str(self.root)), 1)

    def test_windows_batch_wrapper_rejected(self):
        with self.assertRaisesRegex(ValueError, "codex.exe"):
            launch.validate_binary("codex.cmd", "win32")
        launch.validate_binary("codex.exe", "win32")

    def test_dry_run_with_selection_does_not_start_process(self):
        self.write_selection()
        out = io.StringIO()
        with redirect_stdout(out), patch.object(launch, "ROOT", self.root), \
             patch.object(launch.shutil, "which", return_value="codex"), \
             patch.object(launch.subprocess, "run") as run:
            self.assertEqual(launch.main(["--book", str(self.book), "--dry-run"]), 0)
            run.assert_not_called()
        self.assertIn("future-leader-42", out.getvalue())

    def test_target_language_is_forwarded_and_cannot_change_on_resume(self):
        selection_path = self.write_selection()
        selection_path.write_text(json.dumps(self.selection() | {"target_language": "fr"}), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out), patch.object(launch, "ROOT", self.root), \
             patch.object(launch.shutil, "which", return_value="codex"):
            self.assertEqual(launch.main(["--book", str(self.book),
                                          "--target-language", "fr", "--dry-run"]), 0)
        self.assertIn('Язык перевода книги: "fr"', out.getvalue())
        book_dir = launch.resolve_book_dir(self.root, self.book, None)
        state = book_dir / "work/state.json"
        state.write_text(json.dumps({"target_language": "fr"}), encoding="utf-8")
        self.assertEqual(launch.resolve_target_language(book_dir, None), "fr")
        with self.assertRaisesRegex(ValueError, "нельзя менять"):
            launch.resolve_target_language(book_dir, "de")

    def test_check_rejects_selection_for_another_target_language(self):
        selection_path = self.write_selection()
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err), \
             patch.object(launch, "ROOT", self.root):
            result = launch.main(["--book", str(self.book), "--target-language", "fr",
                                  "--selection", str(selection_path), "--check"])
        self.assertEqual(result, 2)
        self.assertIn("другого языка", err.getvalue())

    def test_check_does_not_start_process_or_catalog(self):
        with redirect_stdout(io.StringIO()), patch.object(launch, "ROOT", self.root), \
             patch.object(launch, "query_catalog") as catalog, \
             patch.object(launch.subprocess, "run") as run:
            self.assertEqual(launch.main(["--check"]), 0)
            run.assert_not_called()
            catalog.assert_not_called()

    def test_catalog_stdout_is_parseable_json(self):
        fixture = self.root / "catalog.json"
        fixture.write_text(json.dumps(self.selection()["catalog"]), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(launch, "ROOT", self.root):
            self.assertEqual(launch.main(["--catalog", "--catalog-file", str(fixture)]), 0)
        self.assertEqual(json.loads(out.getvalue())["models"][0]["id"], "future-leader-42")
        self.assertIn("не выполнялись", err.getvalue())

    def test_no_selection_runs_one_preparation_then_validated_translation(self):
        destination = launch.resolve_book_dir(self.root, self.book, None)
        selection_path = destination / "work/model-selection.json"
        def write_selection(*_args, **_kwargs):
            selection_path.parent.mkdir(parents=True, exist_ok=True)
            selection_path.write_text(json.dumps(self.selection()), encoding="utf-8")
            return type("Result", (), {"returncode": 0})()
        with patch.object(launch, "ROOT", self.root), \
             patch.object(launch.shutil, "which", return_value="codex"), \
             patch.object(launch, "query_catalog", return_value=self.selection()["catalog"]) as catalog, \
             patch.object(launch.subprocess, "run", side_effect=write_selection) as run:
            self.assertEqual(launch.main(["--book", str(self.book)]), 0)
            self.assertEqual(run.call_count, 2)
            catalog.assert_called_once()
            prepare_command = run.call_args_list[0].args[0]
            full_command = run.call_args_list[1].args[0]
            self.assertIn("exec", prepare_command)
            self.assertIn("--skip-git-repo-check", prepare_command)
            self.assertIn("--add-dir", prepare_command)
            self.assertNotIn("exec", full_command)
        self.assertTrue(selection_path.is_file())

    def test_dry_run_without_selection_is_preparation_only(self):
        with redirect_stdout(io.StringIO()) as out, patch.object(launch, "ROOT", self.root), \
             patch.object(launch.subprocess, "run") as run:
            self.assertEqual(launch.main(["--book", str(self.book), "--dry-run"]), 0)
            run.assert_not_called()
        self.assertIn("подготовку", out.getvalue())


if __name__ == "__main__":
    unittest.main()
