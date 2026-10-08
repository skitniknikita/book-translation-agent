"""Integration tests for the local Pandoc EPUB builder."""
from __future__ import annotations

import base64
import importlib.util
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".agents/skills/translate-book/scripts/epub_builder.py"
spec = importlib.util.spec_from_file_location("epub_builder", MODULE_PATH)
epub_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(epub_builder)


class EpubBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.book = Path(self.temp.name) / "Автор — Тестовая книга"
        (self.book / "assets").mkdir(parents=True)
        # A valid one-pixel PNG, stored locally as an authorized book asset.
        (self.book / "assets/pixel.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
            "0WJg3gAAAABJRU5ErkJggg=="
        ))
        self.glossary = self.book / "00_Глоссарий.md"
        self.translation = self.book / "01_Перевод.md"
        self.metadata = self.book / "metadata.json"
        self.output = self.book / "Автор — Тестовая книга.epub"
        self.glossary.write_text("Термин — принятое решение.", encoding="utf-8")
        self.translation.write_text(
            "# Глава\n\n"
            "::: {#bt-heading}\n\n"
            "Русский текст с устойчивым термином и ссылкой на примечание.[^note]\n\n"
            ":::\n\n"
            "::: {#bt-table}\n\n"
            "| Понятие | Значение |\n| --- | --- |\n| форма | содержание |\n\n"
            "![Локальная схема](assets/pixel.png)\n\n"
            ":::\n\n"
            "[^note]: Текст сноски тоже обязан попасть в EPUB.\n",
            encoding="utf-8",
        )
        self.write_metadata()

    def tearDown(self):
        self.temp.cleanup()

    def write_metadata(self, **changes):
        data = {
            "title": "Тестовая книга",
            "creator": "Тестовый автор",
            "language": "ru",
            "rights": "Не для коммерческого распространения.",
            "source": "Локальный исходник, 2026.",
            "unofficial_note": "Неофициальный рабочий перевод.",
        }
        data.update(changes)
        import json
        self.metadata.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def build(self, *, css=None, expected_ids=("bt-heading", "bt-table")):
        return epub_builder.build_epub(
            self.book, self.translation, self.glossary, self.metadata, self.output, css,
            expected_ids=expected_ids,
        )

    def test_builds_valid_epub_with_glossary_notes_and_local_image(self):
        report = self.build()
        self.assertEqual(report["output"], str(self.output.resolve()))
        self.assertEqual(report["epub"], str(self.output.resolve()))
        self.assertTrue(report["reverse_text_checked"])
        self.assertEqual(report["expected_ids"], 2)
        self.assertGreater(report["source_word_count"], 10)
        self.assertEqual(
            report["input_resources"],
            [{"path": "assets/pixel.png", "sha256": report["input_resources"][0]["sha256"]}],
        )
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.infolist()[0].filename, "mimetype")
            self.assertEqual(archive.infolist()[0].compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.read("mimetype"), b"application/epub+zip")

    def test_missing_local_asset_preserves_previous_epub(self):
        self.translation.write_text("![Нет файла](assets/missing.png)", encoding="utf-8")
        self.output.write_bytes(b"previous-good-epub")
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "не найден"):
            self.build()
        self.assertEqual(self.output.read_bytes(), b"previous-good-epub")

    def test_broken_internal_reference_preserves_previous_epub(self):
        self.translation.write_text(
            "::: {#bt-heading}\n\n[Переход](#missing-anchor)\n\n:::", encoding="utf-8"
        )
        self.output.write_bytes(b"previous-good-epub")
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "отсутствующему ID"):
            self.build()
        self.assertEqual(self.output.read_bytes(), b"previous-good-epub")

    def test_incomplete_metadata_preserves_previous_epub(self):
        self.write_metadata(rights="")
        self.output.write_bytes(b"previous-good-epub")
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "rights"):
            self.build()
        self.assertEqual(self.output.read_bytes(), b"previous-good-epub")

    def test_accepts_yaml_metadata(self):
        yaml_metadata = self.book / "metadata.yaml"
        yaml_metadata.write_text(
            "title: Тестовая книга\n"
            "creator:\n  - Тестовый автор\n"
            "language: ru\n"
            "rights: Не для коммерческого распространения.\n"
            "source: Локальный исходник, 2026.\n"
            "unofficial_note: Неофициальный рабочий перевод.\n",
            encoding="utf-8",
        )
        report = epub_builder.build_epub(
            self.book, self.translation, self.glossary, yaml_metadata, self.output,
            expected_ids=("bt-heading", "bt-table"),
        )
        self.assertTrue(report["reverse_text_checked"])

    def test_remote_reference_image_is_rejected_before_epub_conversion(self):
        self.translation.write_text(
            "![Удалённое изображение][figure]\n\n[figure]: https://example.test/image.png\n",
            encoding="utf-8",
        )
        original = epub_builder._run_pandoc
        calls = []

        def spy(*args, **kwargs):
            calls.append(args[1])
            return original(*args, **kwargs)

        with patch.object(epub_builder, "_run_pandoc", side_effect=spy):
            with self.assertRaisesRegex(epub_builder.EpubBuildError, "Внешний"):
                self.build()
        self.assertFalse(any("--to=epub3" in args for args in calls))

    def test_unquoted_raw_image_and_svg_dependency_are_rejected_before_conversion(self):
        self.translation.write_text("<img src=https://example.test/pixel.png>", encoding="utf-8")
        original = epub_builder._run_pandoc
        calls = []

        def spy(*args, **kwargs):
            calls.append(args[1])
            return original(*args, **kwargs)

        with patch.object(epub_builder, "_run_pandoc", side_effect=spy):
            with self.assertRaisesRegex(epub_builder.EpubBuildError, "Внешний"):
                self.build()
        self.assertFalse(any("--to=epub3" in args for args in calls))

        (self.book / "assets/external.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.test/x.png"/></svg>',
            encoding="utf-8",
        )
        self.translation.write_text("![SVG](assets/external.svg)", encoding="utf-8")
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "SVG не может"):
            self.build()

        self.translation.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.test/x.png"/></svg>',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "Внешний"):
            self.build()

    def test_raw_style_and_stylesheet_dependencies_are_rejected_before_conversion(self):
        self.translation.write_text("<style>p { background: url(https://example.test/x.png); }</style>", encoding="utf-8")
        original = epub_builder._run_pandoc
        calls = []

        def spy(*args, **kwargs):
            calls.append(args[1])
            return original(*args, **kwargs)

        with patch.object(epub_builder, "_run_pandoc", side_effect=spy):
            with self.assertRaisesRegex(epub_builder.EpubBuildError, "CSS EPUB"):
                self.build()
        self.assertFalse(any("--to=epub3" in args for args in calls))

        self.translation.write_text(
            "::: {#bt-heading}\n\nБезопасный текст.\n\n:::\n\n"
            "::: {#bt-table}\n\nТабличный блок.\n\n:::\n",
            encoding="utf-8",
        )
        stylesheet = self.book / "epub.css"
        stylesheet.write_text('@import url("https://example.test/font.css");', encoding="utf-8")
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "@import"):
            self.build(css=stylesheet)

    def test_multichapter_endnote_table_image_and_stylesheet_round_trip(self):
        stylesheet = self.book / "epub.css"
        stylesheet.write_text("body { font-family: serif; }", encoding="utf-8")
        self.translation.write_text(
            "# Первая глава\n\n"
            "::: {#bt-first}\n\n"
            "Первый русский блок со сноской.[^late-note]\n\n:::\n\n"
            "# Вторая глава\n\n"
            "::: {#bt-second}\n\n"
            "| Понятие | Значение |\n| --- | --- |\n| вопрос | ответ |\n\n"
            "![Схема](assets/pixel.png)\n\n:::\n\n"
            "[^late-note]: Поздняя сноска после второй главы.\n",
            encoding="utf-8",
        )
        report = self.build(css=stylesheet, expected_ids=("bt-first", "bt-second"))
        self.assertTrue(report["reverse_text_checked"])
        self.assertEqual(report["expected_ids"], 2)
        self.assertEqual(
            [item["path"] for item in report["input_resources"]],
            ["assets/pixel.png", "epub.css"],
        )


if __name__ == "__main__":
    unittest.main()
