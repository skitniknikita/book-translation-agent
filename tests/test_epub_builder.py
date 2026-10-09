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

    def test_french_epub_uses_french_publication_labels(self):
        self.glossary.write_text("Seuil — terme retenu.", encoding="utf-8")
        self.translation.write_text("# Chapitre\n\nTexte français.\n", encoding="utf-8")
        self.write_metadata(
            title="Livre de test", creator="Auteur de test", language="fr",
            rights="Usage de test.", source="Source de test.",
            unofficial_note="Traduction non officielle.",
        )
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "glossary_title"):
            self.build(expected_ids=())
        self.write_metadata(
            title="Livre de test", creator="Auteur de test", language="fr",
            rights="Usage de test.", source="Source de test.",
            unofficial_note="Traduction non officielle.",
            glossary_title="Glossaire", publication_title="Informations sur l’édition",
            source_label="Source originale", rights_label="Droits",
            translation_status_label="Statut de la traduction",
        )
        report = self.build(expected_ids=())
        self.assertTrue(report["reverse_text_checked"])
        with zipfile.ZipFile(self.output) as archive:
            xhtml = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist()
                              if name.endswith(".xhtml"))
        self.assertIn("Glossaire", xhtml)
        self.assertIn("Informations sur l’édition", xhtml)
        self.assertNotIn("Сведения об издании", xhtml)
        previous = self.output.read_bytes()
        with self.assertRaisesRegex(epub_builder.EpubBuildError, "Язык EPUB"):
            epub_builder.build_epub(self.book, self.translation, self.glossary,
                                    self.metadata, self.output, expected_language="de")
        self.assertEqual(self.output.read_bytes(), previous)

    def test_repairs_pandoc_directory_only_toc_link(self):
        candidate = self.book / "broken-nav.epub"
        container = (b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                     b'<rootfiles><rootfile full-path="EPUB/content.opf"/>'
                     b'</rootfiles></container>')
        opf = (b'<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
               b'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
               b'<item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
               b'<item id="body" href="text/chapter.xhtml" media-type="application/xhtml+xml"/>'
               b'</manifest><spine><itemref idref="body"/></spine></package>')
        nav = (b'<html xmlns="http://www.w3.org/1999/xhtml"><body><nav>'
               b'<a href="text/#chapter">Chapter</a></nav></body></html>')
        ncx = (b'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
               b'<navPoint><content src="text/#chapter"/></navPoint></navMap></ncx>')
        body = (b'<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                b'<h1 id="chapter">Chapter</h1></body></html>')
        with zipfile.ZipFile(candidate, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("EPUB/content.opf", opf)
            archive.writestr("EPUB/nav.xhtml", nav)
            archive.writestr("EPUB/toc.ncx", ncx)
            archive.writestr("EPUB/text/chapter.xhtml", body)
        epub_builder._repair_directory_toc_links(candidate)
        with zipfile.ZipFile(candidate) as archive:
            self.assertIn(b'text/chapter.xhtml#chapter', archive.read("EPUB/nav.xhtml"))
            self.assertIn(b'text/chapter.xhtml#chapter', archive.read("EPUB/toc.ncx"))
            self.assertEqual(archive.infolist()[0].filename, "mimetype")
            self.assertEqual(archive.infolist()[0].compress_type, zipfile.ZIP_STORED)

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

    def assert_rejected_before_writer(self, pattern):
        original = epub_builder._run_pandoc
        calls = []

        def spy(*args, **kwargs):
            calls.append(args[1])
            return original(*args, **kwargs)

        self.output.write_bytes(b"previous-good-epub")
        with patch.object(epub_builder, "_run_pandoc", side_effect=spy):
            with self.assertRaisesRegex(epub_builder.EpubBuildError, pattern):
                self.build(expected_ids=())
        self.assertFalse(any("--to=epub3" in args for args in calls))
        self.assertEqual(self.output.read_bytes(), b"previous-good-epub")

    def test_cross_file_reference_cannot_expose_outside_file_or_fetch_url(self):
        outside = Path(self.temp.name) / "synthetic-secret.png"
        outside.write_bytes((self.book / "assets/pixel.png").read_bytes() + b"SYNTHETIC SECRET")
        self.glossary.write_text("Термин.\n\n![Схема][hidden]", encoding="utf-8")
        for target in (str(outside), "https://example.test/track.png"):
            with self.subTest(target=target):
                self.translation.write_text(
                    "# Глава\n\nАвторский текст.\n\n[hidden]: " + target, encoding="utf-8"
                )
                self.assert_rejected_before_writer("Внешний|пределы")

    def test_nested_markdown_uses_checked_root_resource_not_source_folder(self):
        nested = self.book / "chapters"
        nested.mkdir()
        self.translation = nested / "translation.md"
        self.translation.write_text("# Глава\n\n![Схема](pixel.png)", encoding="utf-8")
        image = (self.book / "assets/pixel.png").read_bytes()
        (nested / "pixel.png").write_bytes(image + b"DECOY")
        (self.book / "pixel.png").write_bytes(image)
        report = self.build(expected_ids=())
        self.assertEqual([x["path"] for x in report["input_resources"]], ["pixel.png"])
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(
                [archive.read(x) for x in archive.namelist() if "/media/" in x], [image]
            )
        outside = Path(self.temp.name) / "synthetic-secret.png"
        outside.write_bytes(image + b"SYNTHETIC SECRET")
        (self.book / "pixel.png").unlink()
        (self.book / "pixel.png").symlink_to(outside)
        self.assert_rejected_before_writer("пределы")

    def test_metadata_images_checked_before_writer(self):
        outside = Path(self.temp.name) / "synthetic-secret.png"
        outside.write_bytes((self.book / "assets/pixel.png").read_bytes())
        for target in (str(outside), "https://example.test/track.png"):
            with self.subTest(target=target):
                self.write_metadata(title=f"![Схема]({target})")
                self.assert_rejected_before_writer("Внешний|пределы")

    def test_native_markdown_attributes_cannot_embed_resources_or_handlers(self):
        payloads = (
            ('::: {style="background-image: url(https://example.test/track.png)"}\n\nТекст.\n\n:::', "CSS EPUB"),
            ('[Текст.]{onclick="alert(1)"}', "HTML-обработчик"),
            ('::: {onclick="alert(1)"}\n\nТекст.\n\n:::', "HTML-обработчик"),
            ('<svg xmlns="http://www.w3.org/2000/svg"><path fill="url(https://example.test/fill.svg#x)"/></svg>', "CSS EPUB"),
            ('<video poster="https://example.test/track.png"></video>', "Внешний"),
            ('<meta http-equiv="refresh" content="0;url=https://example.test/redirect" />', "raw HTML-тег"),
            ('<svg:svg xmlns:svg="http://www.w3.org/2000/svg"><svg:script>alert(1)</svg:script></svg:svg>', "raw HTML-тег"),
            ('<svg:svg xmlns:svg="http://www.w3.org/2000/svg"><svg:set attributeName="href" to="https://example.test/track.png"/></svg:svg>', "raw HTML-тег"),
        )
        for payload, pattern in payloads:
            with self.subTest(payload=payload):
                self.translation.write_text("# Глава\n\n" + payload, encoding="utf-8")
                self.assert_rejected_before_writer(pattern)

    def test_css_escaped_and_alternate_resource_functions_are_rejected(self):
        stylesheet = self.book / "epub.css"
        payloads = (
            r'p { background-image: u\72l(https://example.test/track.png); }',
            r'@\69mport "https://example.test/style.css";',
            'p { background-image: image-set("https://example.test/track.png" 1x); }',
            'p { background-image: -webkit-image-set("https://example.test/track.png" 1x); }',
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                stylesheet.write_text(payload, encoding="utf-8")
                with self.assertRaisesRegex(epub_builder.EpubBuildError, "CSS EPUB"):
                    self.build(css=stylesheet)

    def test_svg_animation_dtd_and_stylesheet_pi_are_rejected_before_writer(self):
        svg = self.book / "assets/static.svg"
        payloads = (
            '<image id="x" href="#x"/><set href="#x" attributeName="href" to="https://example.test/track.png" begin="0s"/>',
            '<animate attributeName="href" values="#x;https://example.test/track.png"/>',
        )
        documents = [
            '<svg xmlns="http://www.w3.org/2000/svg">' + payload + '</svg>' for payload in payloads
        ]
        documents.extend((
            '<?xml-stylesheet type="text/css" href="https://example.test/style.css"?><svg xmlns="http://www.w3.org/2000/svg"/>',
            '<!DOCTYPE svg SYSTEM "https://example.test/remote.dtd"><svg xmlns="http://www.w3.org/2000/svg"/>',
        ))
        self.translation.write_text("# Глава\n\n![Схема](assets/static.svg)", encoding="utf-8")
        for document in documents:
            for encoding in ("utf-8", "utf-16"):
                with self.subTest(document=document, encoding=encoding):
                    svg.write_text(document, encoding=encoding)
                    self.assert_rejected_before_writer("SVG")

    def test_static_svg_and_self_contained_css_remain_supported(self):
        svg = self.book / "assets/static.svg"
        svg.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            '<defs><linearGradient id="gradient"><stop offset="0" stop-color="red"/></linearGradient></defs>'
            '<rect width="10" height="10" fill="url(#gradient)"/></svg>', encoding="utf-8"
        )
        self.translation.write_text(
            '# Глава\n\n[Текст.]{style="font-variant: small-caps"}\n\n'
            '[Источник](https://example.test/source)\n\n![Схема](assets/static.svg)', encoding="utf-8"
        )
        css = self.book / "epub.css"
        css.write_text('/* Обычный комментарий. */ body { font-family: serif; }', encoding="utf-8")
        self.assertTrue(self.build(css=css, expected_ids=())["reverse_text_checked"])


if __name__ == "__main__":
    unittest.main()
