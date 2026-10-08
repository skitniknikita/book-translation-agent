"""Deterministic, offline Markdown-to-EPUB builder for translated books.

The helper deliberately has no knowledge of the translation workflow.  Callers
give it the already-approved Markdown files and (optionally) the stable block
IDs which must survive the EPUB conversion.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile


MIMETYPE = b"application/epub+zip"
CONTAINER_PATH = "META-INF/container.xml"
ALLOWED_META_INF = {CONTAINER_PATH, "META-INF/com.apple.ibooks.display-options.xml"}
XML_NS = "http://www.w3.org/XML/1998/namespace"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
PANDOC = Path("/opt/homebrew/bin/pandoc")
_BLOCK_ID = re.compile(r"bt-[A-Za-z0-9_-]+\Z")
_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
_CSS_IMPORT = re.compile(r"@import\b", re.IGNORECASE)
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
_CSS_RESOURCE_FUNCTION = re.compile(r"\b(?:-webkit-)?(?:image-set|image|src)\s*\(", re.IGNORECASE)
_CSS_PRESENTATION_ATTRS = {"fill", "stroke", "filter", "clip-path", "mask", "cursor",
                           "marker", "marker-start", "marker-mid", "marker-end"}


class EpubBuildError(ValueError):
    """Raised when an input is unsafe, Pandoc fails, or the EPUB is invalid."""


def build_epub(
    book_dir: Path,
    translation: Path,
    glossary: Path,
    metadata: Path,
    output: Path,
    css: Path | None = None,
    *,
    expected_ids: Sequence[str] = (),
) -> dict:
    """Build and validate an EPUB, atomically replacing ``output`` on success.

    ``translation``, ``glossary``, ``metadata`` and optional ``css`` must be
    regular files inside ``book_dir``.  The output also stays inside that
    directory, which prevents a Markdown reference from reaching arbitrary
    local files.  ``expected_ids`` accepts the stable ``bt-*`` block IDs from
    the workflow; footnote definitions are intentionally excluded because
    Pandoc owns their anchors.

    The returned report contains only facts established by validation.  Any
    failure leaves both the supplied inputs and an existing good output intact.
    """
    root = Path(book_dir).expanduser().resolve()
    if not root.is_dir():
        raise EpubBuildError(f"Папка книги не найдена: {root}")
    translation = _book_file(root, translation, "перевод")
    glossary = _book_file(root, glossary, "глоссарий")
    metadata = _book_file(root, metadata, "метаданные")
    css_path = _book_file(root, css, "CSS") if css is not None else None
    output = Path(output).expanduser().resolve()
    _inside(root, output, "Итоговый EPUB должен находиться в папке книги")
    if output.suffix.lower() != ".epub":
        raise EpubBuildError("Итоговый файл должен иметь расширение .epub")

    expected = tuple(expected_ids)
    if len(set(expected)) != len(expected):
        raise EpubBuildError("Ожидаемые ID блоков повторяются")
    invalid = [item for item in expected if not _BLOCK_ID.fullmatch(item)]
    if invalid:
        raise EpubBuildError("Недопустимый ID блока: " + ", ".join(invalid))

    pandoc = _pandoc_path()
    resources: set[Path] = set()
    if css_path is not None:
        _reject_unsafe_css(css_path)
        resources.add(css_path)
    metadata_values = _metadata_values(metadata)
    required = ("title", "creator", "language", "rights", "source", "unofficial_note")
    missing = [key for key in required if not metadata_values.get(key)]
    if missing:
        raise EpubBuildError("В метаданных не заполнены: " + ", ".join(missing))

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".epub-build-", dir=root) as temporary:
        work = Path(temporary)
        combined = work / "book.md"
        canonical_metadata = work / "metadata.yaml"
        checked_document = work / "book.json"
        candidate = work / "book.epub"
        combined.write_text(
            _combined_markdown(glossary, translation, metadata_values), encoding="utf-8"
        )
        # JSON is valid YAML.  This keeps metadata handling dependency-free and
        # normalizes Pandoc's `author`/`lang` field names for EPUB's DC fields.
        canonical_metadata.write_text(
            json.dumps(_canonical_metadata(metadata_values), ensure_ascii=False), encoding="utf-8"
        )
        # Parse the final document once, including shared reference definitions
        # and metadata.  The writer receives this exact validated AST, rather
        # than reparsing a different combination of Markdown files.
        rendered = _run_pandoc(
            pandoc,
            ["--from=markdown+fenced_divs+footnotes+pipe_tables", "--to=json",
             "--standalone", "--metadata-file", str(canonical_metadata), str(combined)],
            cwd=root,
        )
        try:
            document = json.loads(rendered)
        except json.JSONDecodeError as error:
            raise EpubBuildError("Pandoc вернул некорректный AST книги") from error
        resources.update(_preflight_document(root, document, root / "book.md"))
        checked_document.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        _run_pandoc(
            pandoc,
            [
                "--from=json",
                "--to=epub3",
                "--standalone",
                "--toc",
                "--epub-title-page",
                "--resource-path",
                str(root),
                "--output",
                str(candidate),
                str(checked_document),
            ]
            + (["--css", str(css_path)] if css_path is not None else []),
            cwd=root,
        )
        source_plain = _pandoc_plain(pandoc, checked_document, cwd=root, input_format="json")
        report = validate_epub(
            candidate,
            expected_ids=expected,
            required_metadata=metadata_values,
            source_plain=source_plain,
            pandoc=pandoc,
        )
        # The temporary file is in book_dir, so replace is atomic on the same
        # filesystem.  Nothing touches a previous EPUB before validation ends.
        os.replace(candidate, output)
    report["epub"] = str(output)
    report["output"] = str(output)
    report["input_resources"] = _resource_report(root, resources)
    return report


def validate_epub(
    epub: Path,
    *,
    expected_ids: Sequence[str] = (),
    required_metadata: dict[str, object] | None = None,
    source_plain: str | None = None,
    pandoc: Path | None = None,
) -> dict:
    """Validate the EPUB structure and return a compact audit report.

    This function is public to allow a workflow to re-check a saved EPUB.  It
    performs no writes.  When ``source_plain`` is supplied it also checks that
    the reverse-read EPUB text retains the full normalized word sequence,
    including footnotes.
    """
    epub = Path(epub).expanduser().resolve()
    if not epub.is_file():
        raise EpubBuildError(f"EPUB не найден: {epub}")
    expected = tuple(expected_ids)
    if len(set(expected)) != len(expected) or any(not _BLOCK_ID.fullmatch(x) for x in expected):
        raise EpubBuildError("Некорректный список ожидаемых ID блоков")

    with zipfile.ZipFile(epub) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise EpubBuildError(f"Повреждён ZIP-элемент EPUB: {bad_member}")
        members = [info.filename for info in archive.infolist()]
        if not members:
            raise EpubBuildError("EPUB пуст")
        first = archive.infolist()[0]
        if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED:
            raise EpubBuildError("Первым несжатым элементом EPUB должен быть mimetype")
        if archive.read("mimetype") != MIMETYPE:
            raise EpubBuildError("Некорректный MIME-тип EPUB")
        _validate_archive_paths(members)
        if CONTAINER_PATH not in members:
            raise EpubBuildError("В EPUB отсутствует META-INF/container.xml")
        container = _parse_xml(archive.read(CONTAINER_PATH), CONTAINER_PATH)
        rootfile = container.find(f".//{{{CONTAINER_NS}}}rootfile")
        if rootfile is None or not rootfile.get("full-path"):
            raise EpubBuildError("container.xml не указывает OPF")
        opf_path = _normal_zip_path(rootfile.get("full-path", ""))
        if opf_path not in members:
            raise EpubBuildError("OPF из container.xml отсутствует в EPUB")
        opf = _parse_xml(archive.read(opf_path), opf_path)
        if opf.tag != f"{{{OPF_NS}}}package":
            raise EpubBuildError("Корневой элемент OPF должен быть package")
        manifest, spine = _parse_opf(opf, opf_path, members)
        _validate_manifest_completeness(archive, members, opf_path, manifest)
        _validate_required_metadata(opf, required_metadata)

        xml_documents: dict[str, ET.Element] = {}
        ids_by_document: dict[str, set[str]] = {}
        expected_locations: dict[str, list[str]] = {}
        for item in manifest.values():
            path = item["path"]
            if _is_xml(item["media_type"], path):
                root = _parse_xml(archive.read(path), path)
                xml_documents[path] = root
                document_ids: set[str] = set()
                for element in root.iter():
                    value = element.get("id") or element.get(f"{{{XML_NS}}}id")
                    if value:
                        if value in document_ids:
                            raise EpubBuildError(f"В XHTML/XML повторяется ID {value!r}: {path}")
                        document_ids.add(value)
                        if value in expected:
                            expected_locations.setdefault(value, []).append(path)
                ids_by_document[path] = document_ids
        _validate_navigation(manifest, spine)
        _validate_links(xml_documents, manifest, ids_by_document)
        missing = [identifier for identifier in expected if len(expected_locations.get(identifier, [])) != 1]
        if missing:
            raise EpubBuildError("В EPUB потеряны или повторяются ID блоков: " + ", ".join(missing))

        report = {
            "epub": str(epub),
            "opf": opf_path,
            "manifest_items": len(manifest),
            "spine_items": len(spine),
            "document_ids": sum(len(ids) for ids in ids_by_document.values()),
            "expected_ids": len(expected),
            "reverse_text_checked": False,
        }

    if source_plain is not None:
        reader = pandoc or _pandoc_path()
        reverse = _pandoc_plain(reader, epub, cwd=epub.parent, input_format="epub")
        source_words = _words(source_plain)
        reverse_words = _words(reverse)
        if not _is_subsequence(source_words, reverse_words):
            raise EpubBuildError(
                "Обратное чтение EPUB не сохранило порядок всех слов исходной разметки"
            )
        report.update(
            {
                "reverse_text_checked": True,
                "source_word_count": len(source_words),
                "reverse_word_count": len(reverse_words),
            }
        )
    return report


def _book_file(root: Path, value: Path | None, label: str) -> Path:
    if value is None:
        raise EpubBuildError(f"Не указан файл: {label}")
    path = Path(value).expanduser().resolve()
    _inside(root, path, f"Файл «{label}» должен находиться в папке книги")
    if not path.is_file():
        raise EpubBuildError(f"Файл «{label}» не найден: {path}")
    return path


def _inside(root: Path, path: Path, message: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise EpubBuildError(message) from error


def _pandoc_path() -> Path:
    if PANDOC.is_file():
        return PANDOC
    found = shutil.which("pandoc")
    if not found:
        raise EpubBuildError("Pandoc не найден; EPUB не был собран")
    return Path(found)


def _run_pandoc(binary: Path, args: list[str], *, cwd: Path, input_text: str | None = None) -> str:
    try:
        completed = subprocess.run(
            [str(binary), *args],
            cwd=cwd,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise EpubBuildError(f"Pandoc не удалось запустить: {error}") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "неизвестная ошибка"
        raise EpubBuildError(f"Pandoc не собрал EPUB: {detail}")
    return completed.stdout


def _metadata_values(metadata: Path) -> dict[str, object]:
    if metadata.suffix.lower() == ".json":
        try:
            raw = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EpubBuildError(f"Не удалось прочитать JSON-метаданные: {error}") from error
        if not isinstance(raw, dict):
            raise EpubBuildError("JSON-метаданные должны быть объектом")
        flattened = {str(key): _plain_value(value) for key, value in raw.items()}
    else:
        pandoc = _pandoc_path()
        rendered = _run_pandoc(
            pandoc,
            ["--from=markdown", "--to=json", "--standalone", "--metadata-file", str(metadata), "-"],
            cwd=metadata.parent,
            input_text="",
        )
        try:
            document = json.loads(rendered)
        except json.JSONDecodeError as error:
            raise EpubBuildError("Pandoc вернул некорректные YAML-метаданные") from error
        flattened = {str(key): _pandoc_meta_value(value) for key, value in document.get("meta", {}).items()}

    def first(*keys: str) -> str:
        for key in keys:
            value = flattened.get(key)
            if isinstance(value, list):
                value = "; ".join(part for part in value if part)
            if value is not None and str(value).strip():
                return _normalized_text(str(value))
        return ""

    creators = flattened.get("creator", flattened.get("author", flattened.get("authors", [])))
    if isinstance(creators, str):
        creators = [creators]
    elif not isinstance(creators, list):
        creators = [str(creators)] if creators else []
    return {
        "title": first("title"),
        "creator": [_normalized_text(str(value)) for value in creators if str(value).strip()],
        "language": first("language", "lang"),
        "rights": first("rights"),
        "source": first("source", "original_source"),
        "unofficial_note": first("unofficial_note", "unofficial-note", "translation_note"),
    }


def _plain_value(value: object) -> object:
    if isinstance(value, list):
        return [str(_plain_value(item)).strip() for item in value]
    if isinstance(value, dict):
        return " ".join(str(_plain_value(item)) for item in value.values())
    return "" if value is None else str(value)


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _pandoc_meta_value(value: object) -> object:
    if not isinstance(value, dict):
        return _plain_value(value)
    tag = value.get("t")
    content = value.get("c")
    if tag == "MetaList" and isinstance(content, list):
        return [_pandoc_meta_value(item) for item in content]
    return _pandoc_inline_text(content)


def _pandoc_inline_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(part for part in (_pandoc_inline_text(item) for item in value) if part)
    if isinstance(value, dict):
        tag = value.get("t")
        content = value.get("c")
        if tag in {"Space", "SoftBreak", "LineBreak"}:
            return " "
        if tag in {"Str", "MetaString"} and isinstance(content, str):
            return content
        return _pandoc_inline_text(content)
    return ""


def _canonical_metadata(values: dict[str, object]) -> dict[str, object]:
    return {
        "title": values["title"],
        "author": values["creator"],
        "lang": values["language"],
        "language": values["language"],
        "rights": values["rights"],
        "source": values["source"],
    }


def _combined_markdown(glossary: Path, translation: Path, values: dict[str, object]) -> str:
    glossary_text = glossary.read_text(encoding="utf-8")
    translation_text = translation.read_text(encoding="utf-8")
    source = _html_text(str(values["source"]))
    rights = _html_text(str(values["rights"]))
    note = _html_text(str(values["unofficial_note"]))
    return (
        "# Глоссарий {#glossary}\n\n"
        + glossary_text.strip()
        + "\n\n"
        + translation_text.strip()
        + "\n\n# Сведения об издании {#publication-information}\n\n"
        + f"**Источник оригинала:** <span>{source}</span>  \n"
        + f"**Права:** <span>{rights}</span>  \n"
        + f"**Статус перевода:** <span>{note}</span>\n"
    )


def _html_text(value: str) -> str:
    return html.escape(value, quote=False).replace("\n", " ")


def _preflight_document(root: Path, document: object, path: Path) -> set[Path]:
    """Check the entire final AST before resource-consuming EPUB conversion.

    ``path.parent`` is the writer's resource base, not an original Markdown
    file's folder.  Canonical image paths also prevent a different resource
    search order from substituting an unchecked file.
    """
    resources: set[Path] = set()
    for attrs in _pandoc_attributes(document):
        for name, value in attrs:
            name = name.lower()
            if name.startswith("on"):
                raise EpubBuildError(f"В книге запрещён HTML-обработчик {name}")
            if name == "style" or name in _CSS_PRESENTATION_ATTRS:
                _reject_css_text(value, path.name)
            elif name in {"src", "srcset", "data", "href", "poster", "background"}:
                # Structural Link/Image targets are checked separately.
                # Attr-based resource overrides have no book-formatting use.
                raise EpubBuildError(f"В книге запрещён атрибут ресурса {name}")
    for node in _pandoc_nodes(document):
        if node.get("t") != "Image":
            continue
        content = node.get("c")
        if not isinstance(content, list) or len(content) < 3:
            raise EpubBuildError(f"Некорректное изображение в {path.name}")
        target = content[2]
        if not isinstance(target, list) or not target or not isinstance(target[0], str):
            raise EpubBuildError(f"Некорректный путь изображения в {path.name}")
        checked = _validate_local_resource(root, target[0], path)
        resources.update(checked)
        target[0] = str(next(iter(checked)))
    inspector = _RawHtmlInspector(root, path)
    try:
        for fragment in _raw_html_fragments(document):
            inspector.feed(fragment)
        inspector.close()
    except EpubBuildError:
        raise
    except Exception as error:
        raise EpubBuildError(f"Некорректный raw HTML в {path.name}: {error}") from error
    resources.update(inspector.resources)
    return resources


def _pandoc_attributes(value: object) -> Iterable[list[list[str]]]:
    """Find Pandoc Attr triples, including table cells and metadata nodes."""
    if isinstance(value, dict):
        for child in value.values():
            yield from _pandoc_attributes(child)
    elif isinstance(value, list):
        if (len(value) == 3 and isinstance(value[0], str)
                and isinstance(value[1], list) and all(isinstance(x, str) for x in value[1])
                and isinstance(value[2], list)
                and all(isinstance(x, list) and len(x) == 2
                        and all(isinstance(part, str) for part in x) for x in value[2])):
            yield value[2]
        for child in value:
            yield from _pandoc_attributes(child)


def _pandoc_nodes(value: object) -> Iterable[dict[str, object]]:
    if isinstance(value, dict):
        if isinstance(value.get("t"), str):
            yield value
        for child in value.values():
            yield from _pandoc_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _pandoc_nodes(child)


def _raw_html_fragments(document: object) -> Iterable[str]:
    for node in _pandoc_nodes(document):
        if node.get("t") not in {"RawInline", "RawBlock"}:
            continue
        content = node.get("c")
        if (
            isinstance(content, list)
            and len(content) == 2
            and _pandoc_format_name(content[0]) == "html"
            and isinstance(content[1], str)
        ):
            yield content[1]


def _pandoc_format_name(value: object) -> str:
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict) and value.get("t") == "Format" and isinstance(value.get("c"), str):
        return value["c"].lower()
    return ""


class _RawHtmlInspector(HTMLParser):
    """Reject active/raw embedded content that Pandoc's Markdown AST omits."""

    _RESOURCE_TAGS = {"img", "audio", "video", "source", "object", "embed", "link", "image", "use"}
    _BLOCKED_TAGS = {"script", "iframe", "object", "embed", "form", "input", "button", "meta",
                     "animate", "animatemotion", "animatetransform", "animatecolor", "set", "discard"}

    def __init__(self, root: Path, source: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.root = root
        self.source = source
        self.resources: set[Path] = set()
        self._style_depth = 0
        self._style_chunks: list[str] = []
        self._svg_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower().rsplit(":", 1)[-1]
        if tag in self._BLOCKED_TAGS:
            raise EpubBuildError(f"В {self.source.name} запрещён raw HTML-тег <{tag}>")
        if tag == "style":
            self._style_depth += 1
        if tag == "svg":
            self._svg_depth += 1
        for name, value in attrs:
            name = name.lower().rsplit(":", 1)[-1]
            if name.startswith("on"):
                raise EpubBuildError(f"В {self.source.name} запрещён HTML-обработчик {name}")
            if value is None:
                continue
            if name == "style" or name in _CSS_PRESENTATION_ATTRS:
                _reject_css_text(value, self.source.name)
            elif name == "srcset":
                for candidate in value.split(","):
                    target = candidate.strip().split(maxsplit=1)[0]
                    if target:
                        self.resources.update(_validate_local_resource(self.root, target, self.source))
            elif self._svg_depth and tag != "a" and name in {"src", "data", "href"}:
                if not value.startswith("#"):
                    self.resources.update(_validate_local_resource(self.root, value, self.source))
            elif name in {"src", "data", "poster", "background"} or (tag in self._RESOURCE_TAGS and name == "href"):
                self.resources.update(_validate_local_resource(self.root, value, self.source))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower().rsplit(":", 1)[-1]
        if tag == "style" and self._style_depth:
            self._style_depth -= 1
            if not self._style_depth:
                _reject_css_text("".join(self._style_chunks), self.source.name)
                self._style_chunks.clear()
        if tag == "svg" and self._svg_depth:
            self._svg_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self._style_chunks.append(data)

    def handle_pi(self, data: str) -> None:
        raise EpubBuildError(f"В {self.source.name} запрещены processing instructions")

    def handle_decl(self, decl: str) -> None:
        raise EpubBuildError(f"В {self.source.name} запрещены XML/HTML-декларации")


def _reject_unsafe_css(path: Path) -> None:
    """Keep stylesheet use self-contained and deterministic.

    Pandoc includes the CSS file but does not package dependencies referenced
    from CSS consistently, so accepting imports, web fonts or background URLs
    would make a valid-looking EPUB fetch external data or contain broken
    unmanifested resources.  Fragment-only URLs are harmless SVG references.
    """
    _reject_css_text(path.read_text(encoding="utf-8"), path.name)


def _reject_css_text(text: str, label: str) -> None:
    # CSS escapes can spell resource identifiers (u\\72l, @\\69mport).
    # Book styling does not need escaped identifiers, so reject them rather
    # than relying on a partial CSS tokenizer.  Remove comments before checks.
    if "\\" in text:
        raise EpubBuildError(f"CSS EPUB не может содержать escape-последовательности: {label}")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    if _CSS_IMPORT.search(text):
        raise EpubBuildError(f"CSS EPUB не может содержать @import: {label}")
    if _CSS_RESOURCE_FUNCTION.search(text):
        raise EpubBuildError(f"CSS EPUB не может содержать функции отдельных ресурсов: {label}")
    for _, resource in _CSS_URL.findall(text):
        if resource.strip() and not resource.strip().startswith("#"):
            raise EpubBuildError(
                f"CSS EPUB не может загружать внешние или отдельные ресурсы: {label}"
            )


def _validate_local_resource(root: Path, resource: str, source: Path) -> set[Path]:
    split = urlsplit(resource)
    if split.scheme or split.netloc or resource.startswith("/") or resource.startswith("\\"):
        raise EpubBuildError(f"Внешний или абсолютный ресурс в {source.name}: {resource}")
    relative = unquote(split.path)
    if not relative:
        raise EpubBuildError(f"Пустой путь ресурса в {source.name}")
    resolved = (source.parent / relative).resolve()
    _inside(root, resolved, f"Ресурс выходит за пределы книги: {resource}")
    if not resolved.is_file():
        raise EpubBuildError(f"Локальный ресурс не найден: {resource}")
    if resolved.suffix.lower() == ".svg":
        _validate_svg(resolved)
    return {resolved}


def _validate_svg(path: Path) -> None:
    """SVG is XML, so reject active content and non-local dependencies early."""
    data = path.read_bytes()
    # Default ElementTree silently discards PIs and DTDs.  A parser target
    # rejects them in every supported XML encoding, including UTF-16.
    class StaticSvgBuilder(ET.TreeBuilder):
        def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
            raise EpubBuildError(f"SVG не может содержать DTD: {path.name}")

        def pi(self, target: str, text: str | None = None) -> None:
            raise EpubBuildError(f"SVG не может содержать processing instructions: {path.name}")

    try:
        root = ET.fromstring(data, parser=ET.XMLParser(target=StaticSvgBuilder()))
    except ET.ParseError as error:
        raise EpubBuildError(f"Некорректный XML/XHTML в {path.name}: {error}") from error
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject", "animate", "animatemotion", "animatetransform",
                   "animatecolor", "set", "discard"}:
            raise EpubBuildError(f"В SVG запрещён тег <{tag}>: {path.name}")
        for attr, value in element.attrib.items():
            local = attr.rsplit("}", 1)[-1].lower()
            if local.startswith("on"):
                raise EpubBuildError(f"В SVG запрещён обработчик {local}: {path.name}")
            if local == "style" or local in _CSS_PRESENTATION_ATTRS:
                _reject_css_text(value, path.name)
            elif local in {"href", "src", "data"} and value and not value.startswith("#"):
                raise EpubBuildError(f"SVG не может подключать отдельный ресурс: {path.name}")
        if tag == "style" and element.text:
            _reject_css_text(element.text, path.name)


def _resource_report(root: Path, resources: Iterable[Path]) -> list[dict[str, str]]:
    report: list[dict[str, str]] = []
    for path in sorted({item.resolve() for item in resources}, key=lambda item: str(item)):
        _inside(root, path, "Ресурс находится вне папки книги")
        report.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    return report


def _validate_archive_paths(members: Iterable[str]) -> None:
    seen: set[str] = set()
    for member in members:
        if member in seen:
            raise EpubBuildError(f"Повторяется ZIP-элемент EPUB: {member}")
        seen.add(member)
        _normal_zip_path(member)


def _normal_zip_path(value: str) -> str:
    decoded = unquote(value).replace("\\", "/")
    path = PurePosixPath(decoded)
    if not decoded or path.is_absolute() or ".." in path.parts or decoded.startswith("/"):
        raise EpubBuildError(f"Небезопасный путь в EPUB: {value}")
    return str(path)


def _parse_xml(data: bytes, path: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise EpubBuildError(f"Некорректный XML/XHTML в {path}: {error}") from error


def _parse_opf(root: ET.Element, opf_path: str, members: list[str]) -> tuple[dict[str, dict[str, str]], list[str]]:
    manifest_node = root.find(f"{{{OPF_NS}}}manifest")
    spine_node = root.find(f"{{{OPF_NS}}}spine")
    if manifest_node is None or spine_node is None:
        raise EpubBuildError("В OPF отсутствует manifest или spine")
    manifest: dict[str, dict[str, str]] = {}
    opf_parent = PurePosixPath(opf_path).parent
    for item in manifest_node.findall(f"{{{OPF_NS}}}item"):
        identifier = item.get("id", "")
        href = item.get("href", "")
        media_type = item.get("media-type", "")
        if not identifier or not href or not media_type or identifier in manifest:
            raise EpubBuildError("В OPF есть неполный или повторяющийся элемент manifest")
        path = _resolve_internal_path(str(opf_parent), href)
        if path not in members:
            raise EpubBuildError(f"Элемент manifest отсутствует в ZIP: {href}")
        manifest[identifier] = {
            "path": path,
            "media_type": media_type,
            "properties": item.get("properties", ""),
        }
    spine: list[str] = []
    for itemref in spine_node.findall(f"{{{OPF_NS}}}itemref"):
        identifier = itemref.get("idref", "")
        if identifier not in manifest:
            raise EpubBuildError(f"Spine ссылается на отсутствующий manifest ID: {identifier}")
        spine.append(identifier)
    if not manifest or not spine:
        raise EpubBuildError("Manifest и spine EPUB не должны быть пустыми")
    return manifest, spine


def _validate_manifest_completeness(
    archive: zipfile.ZipFile, members: list[str], opf_path: str, manifest: dict[str, dict[str, str]]
) -> None:
    # Pandoc emits this Apple Books compatibility file.  It is EPUB metadata,
    # not reading content, so it does not belong in OPF's manifest.
    allowed_meta = set(ALLOWED_META_INF) & set(members)
    for path in allowed_meta - {CONTAINER_PATH}:
        _parse_xml(archive.read(path), path)
    accounted = {"mimetype", opf_path, *allowed_meta}
    accounted.update(item["path"] for item in manifest.values())
    extra = sorted(set(members) - accounted)
    if extra:
        raise EpubBuildError("В EPUB есть неописанные manifest ресурсы: " + ", ".join(extra[:8]))


def _validate_required_metadata(root: ET.Element, expected: dict[str, object] | None) -> None:
    metadata = root.find(f"{{{OPF_NS}}}metadata")
    if metadata is None:
        raise EpubBuildError("В OPF отсутствуют метаданные")
    required = {
        "title": "title",
        "creator": "creator",
        "language": "language",
        "rights": "rights",
        "source": "source",
    }
    found: dict[str, list[str]] = {}
    for key, local in required.items():
        found[key] = [node.text.strip() for node in metadata.findall(f"{{{DC_NS}}}{local}") if node.text and node.text.strip()]
        if not found[key]:
            raise EpubBuildError(f"В OPF отсутствует обязательное dc:{local}")
    if expected is None:
        return
    checks = {
        "title": [str(expected.get("title", ""))],
        "creator": [str(value) for value in expected.get("creator", [])],
        "language": [str(expected.get("language", ""))],
        "rights": [str(expected.get("rights", ""))],
        "source": [str(expected.get("source", ""))],
    }
    for key, wanted in checks.items():
        for value in wanted:
            if value and value not in found[key]:
                raise EpubBuildError(f"Значение {key!r} в OPF не совпадает с метаданными")


def _is_xml(media_type: str, path: str) -> bool:
    return media_type in {"application/xhtml+xml", "application/x-dtbncx+xml", "image/svg+xml"} or path.endswith((".xhtml", ".xml", ".ncx", ".svg"))


def _validate_navigation(manifest: dict[str, dict[str, str]], spine: list[str]) -> None:
    if not any("nav" in item["properties"].split() for item in manifest.values()):
        raise EpubBuildError("В EPUB отсутствует навигационный документ")
    if not any(manifest[item]["media_type"] == "application/xhtml+xml" for item in spine):
        raise EpubBuildError("Spine EPUB не содержит XHTML-документов")
    title_pages = [
        identifier for identifier, item in manifest.items()
        if PurePosixPath(item["path"]).name.lower() in {"title_page.xhtml", "titlepage.xhtml"}
    ]
    if not title_pages or not any(identifier in spine for identifier in title_pages):
        raise EpubBuildError("В EPUB отсутствует титульная страница")


def _validate_links(
    documents: dict[str, ET.Element], manifest: dict[str, dict[str, str]], ids_by_document: dict[str, set[str]]
) -> None:
    available = {item["path"] for item in manifest.values()}
    for document_path, root in documents.items():
        for element in root.iter():
            for attr, value in element.attrib.items():
                local = attr.rsplit("}", 1)[-1]
                if local not in {"href", "src", "data"} or not value:
                    continue
                split = urlsplit(value)
                is_link = local == "href" and element.tag.rsplit("}", 1)[-1].lower() == "a"
                if split.scheme or split.netloc:
                    if is_link and split.scheme.lower() in {"http", "https", "mailto", "tel"}:
                        continue
                    raise EpubBuildError(f"Внешний встроенный ресурс в {document_path}: {value}")
                path_part = unquote(split.path)
                if path_part:
                    target = _resolve_internal_path(str(PurePosixPath(document_path).parent), path_part)
                    if target not in available:
                        raise EpubBuildError(f"Внутренняя ссылка ведёт вне manifest: {value}")
                else:
                    target = document_path
                if split.fragment:
                    if unquote(split.fragment) not in ids_by_document.get(target, set()):
                        raise EpubBuildError(f"Внутренняя ссылка ведёт к отсутствующему ID: {value}")


def _resolve_internal_path(parent: str, href: str) -> str:
    split = urlsplit(href)
    if split.scheme or split.netloc or href.startswith("/"):
        raise EpubBuildError(f"Небезопасная внутренняя ссылка EPUB: {href}")
    # `../styles/foo.css` is a normal EPUB reference from a text subfolder.
    # Normalize it here, while `_normal_zip_path` still rejects literal `..`
    # members in the archive itself and references which escape its root.
    joined = posixpath.normpath(posixpath.join(parent, unquote(split.path)))
    if joined == ".." or joined.startswith("../"):
        raise EpubBuildError(f"Небезопасная внутренняя ссылка EPUB: {href}")
    return _normal_zip_path(joined)


def _pandoc_plain(binary: Path, input_path: Path, *, cwd: Path, input_format: str | None = None) -> str:
    args = ["--to=plain"]
    if input_format:
        args.append(f"--from={input_format}")
    args.append(str(input_path))
    return _run_pandoc(binary, args, cwd=cwd)


def _words(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def _is_subsequence(needles: Sequence[str], haystack: Sequence[str]) -> bool:
    position = 0
    for word in needles:
        while position < len(haystack) and haystack[position] != word:
            position += 1
        if position == len(haystack):
            return False
        position += 1
    return True
