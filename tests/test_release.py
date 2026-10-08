from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release", ROOT / "tools/release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "book-translation-agent"
        self.root.mkdir()
        self.write("README.md", "public documentation\n")
        self.write(".agents/skills/translate-book/SKILL.md", "skill\n")
        self.write(".codex/config.toml", "model = 'example'\n")
        self.write("tests/test_example.py", "test\n")
        self.write("release-files.txt", "README.md\n.agents/skills/translate-book/SKILL.md\n.codex/config.toml\ntests/test_example.py\n")
        release.update_manifest(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_zip_contains_hidden_public_files_and_excludes_unlisted_book_env_and_cache(self):
        self.write("private.epub", "book")
        self.write(".env", "secret")
        self.write("__pycache__/cached.pyc", "cache")
        output = self.root.parent / "release.zip"
        release.build_zip(output, self.root)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), {
                "book-translation-agent/README.md",
                "book-translation-agent/.agents/skills/translate-book/SKILL.md",
                "book-translation-agent/.codex/config.toml",
                "book-translation-agent/tests/test_example.py",
                "book-translation-agent/MANIFEST.sha256",
            })
            self.assertEqual(archive.getinfo("book-translation-agent/README.md").external_attr >> 16, 0o100644)
            self.assertEqual(archive.getinfo("book-translation-agent/README.md").date_time, (1980, 1, 1, 0, 0, 0))

    def test_tampered_allowlisted_file_fails_check(self):
        self.write("README.md", "changed\n")
        with self.assertRaisesRegex(release.ReleaseError, "hash mismatch"):
            release.check_release(self.root)

    def test_allowlist_rejects_traversal_and_symlinks_including_parent(self):
        self.write("release-files.txt", "../outside.txt\n")
        with self.assertRaisesRegex(release.ReleaseError, "relative"):
            release.update_manifest(self.root)
        self.write("release-files.txt", ".env.local\n")
        with self.assertRaisesRegex(release.ReleaseError, "private"):
            release.update_manifest(self.root)
        self.write("release-files.txt", "linked/file.txt\n")
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "file.txt").write_text("outside", encoding="utf-8")
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(release.ReleaseError, "symlink"):
            release.update_manifest(self.root)

    def test_existing_archive_is_preserved_when_check_fails(self):
        output = self.root.parent / "release.zip"
        output.write_bytes(b"old archive")
        self.write("README.md", "changed\n")
        with self.assertRaisesRegex(release.ReleaseError, "hash mismatch"):
            release.build_zip(output, self.root)
        self.assertEqual(output.read_bytes(), b"old archive")

    def test_archive_output_cannot_collide_with_release_input(self):
        original = (self.root / "README.md").read_bytes()
        with self.assertRaises(release.ReleaseError):
            release.build_zip(self.root / "README.md", self.root)
        self.assertEqual((self.root / "README.md").read_bytes(), original)

    def test_allowlist_rejects_private_book_and_account_artifacts(self):
        for path in ("release.zip", "history.bundle", ".npmrc", ".ssh/id_ed25519",
                     "00_Глоссарий.md", "02_Примечания_переводчика.md",
                     "03_Проверки.md", "Book — перевод/metadata.json",
                     "debug.log", ".codex/config.local.toml"):
            with self.subTest(path=path):
                self.write("release-files.txt", path + "\n")
                with self.assertRaises(release.ReleaseError):
                    release.update_manifest(self.root)

    def test_zip_creates_missing_output_directory_after_checking_inputs(self):
        output = self.root.parent / "dist" / "release.zip"
        release.build_zip(output, self.root)
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
