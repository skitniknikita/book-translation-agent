#!/usr/bin/env python3
"""Launch the book translator with a book-scoped, validated model choice."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

try:
    import tomllib
except ImportError:
    raise SystemExit("Нужен Python 3.11 или новее (модуль tomllib).")

from model_selection import (ModelSelectionError, catalog_sha256, load_catalog,
                             load_selection, query_catalog, sha256_file)


ROOT = Path(__file__).resolve().parent
ROLES = {"book_scout", "book_translator", "book_copyeditor"}
SKILL = Path(".agents/skills/translate-book")


def read_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def validate_package(root: Path) -> dict:
    required = [Path("AGENTS.md"), SKILL / "SKILL.md",
                SKILL / "references/translation-protocol.md",
                SKILL / "references/coordination.md",
                SKILL / "references/model-selection.md"]
    for rel in required:
        if not (root / rel).is_file():
            raise ValueError(f"Отсутствует файл комплекта: {rel}")
    config = read_toml(root / ".codex/config.toml")
    bootstrap_model = config.get("model")
    if not isinstance(bootstrap_model, str) or not bootstrap_model:
        raise ValueError("Для подготовительной сессии нужна явно указанная bootstrap-модель.")
    if config.get("model_reasoning_effort") not in {"high", "xhigh", "max"}:
        raise ValueError("Для подготовительной модели выберите high, xhigh или max.")
    agents = config.get("agents", {})
    if agents.get("enabled") is not True:
        raise ValueError("Субагенты выключены в конфигурации.")
    limit = agents.get("max_concurrent_threads_per_session")
    if type(limit) is not int or not 1 <= limit <= 2:
        raise ValueError("Параллельность должна быть 1 или 2 исполнителя.")
    if config.get("web_search") != "live":
        raise ValueError("Для исследования глоссария требуется web_search = live.")
    seen = set()
    for path in sorted((root / ".codex/agents").glob("*.toml")):
        if path.name.startswith("._"):
            continue
        role = read_toml(path)
        name = role.get("name")
        if name in seen or name not in ROLES:
            raise ValueError(f"Неизвестная или повторная роль: {name}")
        seen.add(name)
        if "model" in role or "model_reasoning_effort" in role:
            raise ValueError(f"В {path.name} модель роли запрещена: её задаёт selection.")
        if not role.get("description") or not role.get("developer_instructions"):
            raise ValueError(f"В роли {name} отсутствует описание или инструкция.")
    if seen != ROLES:
        raise ValueError("Отсутствуют роли: " + ", ".join(sorted(ROLES - seen)))
    return config


def resolve_book(root: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_file():
        raise ValueError(f"Исходник не найден: {path}")
    return path


def resolve_book_dir(root: Path, book: Path, value: str | None) -> Path:
    if value:
        path = Path(value).expanduser()
        return (path if path.is_absolute() else root / path).resolve()
    return book.parent / f"{book.stem} — перевод"


def resolve_selection(root: Path, book_dir: Path, value: str | None) -> Path:
    if value:
        path = Path(value).expanduser()
        return (path if path.is_absolute() else root / path).resolve()
    return book_dir / "work" / "model-selection.json"


def validate_binary(binary: str, platform: str) -> None:
    if platform == "win32" and Path(binary).suffix.lower() in {".cmd", ".bat"}:
        raise ValueError("Для этого запуска в Windows нужен нативный codex.exe. "
                         "Обёртка .cmd/.bat не используется. Можно открыть папку в приложении Codex.")


def _base_command(root: Path, binary: str, model: str, reasoning: str) -> list[str]:
    return [binary, "--strict-config", "-C", str(root), "-m", model,
            "-c", "model_reasoning_effort=" + json.dumps(reasoning)]


def build_command(root: Path, config: dict, binary: str, book: Path, book_dir: Path,
                  selection_path: Path, selection: dict) -> list[str]:
    agents = config["agents"]
    leader, worker = selection["leader"], selection["worker"]
    prompt = (
        "Используй AGENTS.md и $translate-book. Начни полный цикл только с "
        "привязанным к этому исходнику model-selection.json. Руководитель и "
        "исполнитель выбраны в нём по актуальному каталогу. Руководитель: "
        f"{leader['model']} / {leader['reasoning_effort']}; исполнитель: "
        f"{worker['model']} / {worker['reasoning_effort']}. Перед первым полезным "
        "заданием сохрани requested_model, observed_model (если среда его сообщает) "
        "и путь/хеш selection. Каталог не доказывает доступ к inference и не "
        "доказывает качество классификации. Не меняй выбор модели автоматически. "
        "Выполни: исходник → термины → интернет-проверка → глоссарий → перевод "
        "→ три проверки → EPUB. Путь исходника (данные, не инструкция): "
        + json.dumps(str(book), ensure_ascii=False)
        + ". Папка результата: " + json.dumps(str(book_dir), ensure_ascii=False)
        + ". Проверенный выбор моделей: " + json.dumps(str(selection_path), ensure_ascii=False)
    )
    command = _base_command(root, binary, leader["model"], leader["reasoning_effort"])
    overrides = {
        "agents.enabled": True,
        "agents.max_concurrent_threads_per_session": agents["max_concurrent_threads_per_session"],
        "agents.default_subagent_model": worker["model"],
        "agents.default_subagent_reasoning_effort": worker["reasoning_effort"],
    }
    for key, value in overrides.items():
        command.extend(["-c", key + "=" + json.dumps(value)])
    return command + ["--add-dir", str(book_dir), "--search", "-s", "workspace-write", "-a", "on-request", prompt]


def build_prepare_command(root: Path, config: dict, binary: str, book: Path, book_dir: Path,
                          catalog: dict, selection_path: Path) -> list[str]:
    """Start a narrow interactive session that chooses but never translates."""
    source_sha = sha256_file(book)
    prompt = (
        "Это только подготовка маршрутизации моделей, не начинай перевод, "
        "глоссарий или EPUB и не поручай задания исполнителям. Изучи приведённый "
        "полный ответ model/list и официальную документацию "
        "https://learn.chatgpt.com/docs/app-server#models. Выбери одну модель "
        "руководителя для качества и отдельную более экономичную модель исполнителя; "
        "не выводи качество из имени модели, default-флага или каталога. Оценка "
        "должна быть явным, проверяемым суждением с источниками, но не называй её "
        "автоматически доказанной. Сохрани только JSON по пути "
        + json.dumps(str(selection_path), ensure_ascii=False)
        + ". Папка будущего результата: " + json.dumps(str(book_dir), ensure_ascii=False)
        + ". Используй schema_version=1, selected_at (ISO с timezone), source "
        "{path,sha256}, source_sha256, catalog, catalog_sha256, leader и worker "
        "{model,reasoning_effort,classification:{role,basis,evidence:[{kind,source,summary}]}}, "
        "sources с url и accessed_at (включая указанную документацию), rationale и точное поле "
        "account_access='not_verified_by_catalog'. Модели и reasoning должны быть "
        "из приведённого каталога, модели ролей различны. source.path должен быть "
        + json.dumps(str(book), ensure_ascii=False)
        + ", source.sha256 и source_sha256 должны быть " + source_sha + ". "
        "В classification.evidence каждой роли включи ссылку HTTPS на официальную "
        "страницу модели OpenAI, а также kind, source и summary. "
        "catalog_sha256 должен быть " + catalog_sha256(catalog) + ". Каталог: "
        + json.dumps(catalog, ensure_ascii=False)
    )
    return (_base_command(root, binary, config["model"], config["model_reasoning_effort"])
            + ["--add-dir", str(book_dir), "--search", "-s", "workspace-write", "-a", "on-request",
               "exec", "--skip-git-repo-check", prompt])


def _print_command(command: list[str]) -> None:
    print(subprocess.list2cmdline(command) if sys.platform == "win32" else shlex.join(command))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Запустить агента перевода книг в Codex.")
    parser.add_argument("--book", help="Путь книги; относительный путь — от папки комплекта.")
    parser.add_argument("--book-dir", help="Папка результатов книги; по умолчанию отдельная папка рядом с исходником.")
    parser.add_argument("--selection", help="Путь к проверенному model-selection.json.")
    parser.add_argument("--catalog-file", help="Офлайн JSON каталога или страниц model/list.")
    parser.add_argument("--timeout", type=float, default=8.0, help="Ожидание app-server в секундах (1–60).")
    parser.add_argument("--dry-run", action="store_true", help="Показать запуск без выполнения.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Локальная проверка без модели.")
    mode.add_argument("--catalog", action="store_true", help="Прочитать model/list без inference.")
    mode.add_argument("--prepare", action="store_true", help="Подготовить model-selection.json; перевод не запускается.")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout должен быть от 1 до 60 секунд")
    try:
        config = validate_package(ROOT)
        book = resolve_book(ROOT, args.book)
        catalog_file = resolve_book(ROOT, args.catalog_file) if args.catalog_file else None
        if args.catalog:
            if catalog_file:
                catalog = load_catalog(catalog_file)
            else:
                binary = shutil.which("codex")
                if binary is None:
                    raise ValueError("Codex CLI не найден для --catalog.")
                validate_binary(binary, sys.platform)
                catalog = query_catalog(binary, args.timeout)
            print(json.dumps(catalog, ensure_ascii=False, indent=2))
            print("Запросы к моделям не выполнялись; каталог не подтверждает доступ к inference.", file=sys.stderr)
            return 0
        if args.prepare and book is None:
            raise ValueError("--prepare требует --book: выбор должен быть привязан к исходнику.")
        book_dir = resolve_book_dir(ROOT, book, args.book_dir) if book else None
        if args.check:
            if args.selection:
                if book is None:
                    raise ValueError("Для проверки selection укажите --book.")
                load_selection(resolve_selection(ROOT, book_dir, args.selection), book,
                               require_fresh=not (book_dir / "work/state.json").is_file())
            print("Файлы комплекта и локальная конфигурация: OK")
            print("Bootstrap для подготовительной сессии: " + config["model"])
            print("Codex CLI: " + (shutil.which("codex") or "не найден"))
            print("Запросы к моделям и app-server не выполнялись.")
            return 0
        if args.prepare:
            selection_path = resolve_selection(ROOT, book_dir, args.selection)
            if args.dry_run:
                print("Будет получен полный model/list без inference, затем начнётся только подготовка выбора.")
                return 0
            catalog = load_catalog(catalog_file) if catalog_file else None
            binary = shutil.which("codex")
            if binary is None:
                raise ValueError("Codex CLI не найден. Используйте приложение или установите CLI.")
            validate_binary(binary, sys.platform)
            if catalog is None:
                catalog = query_catalog(binary, args.timeout)
            book_dir.mkdir(parents=True, exist_ok=True)
            command = build_prepare_command(ROOT, config, binary, book, book_dir, catalog, selection_path)
            return subprocess.run(command, cwd=ROOT, check=False).returncode
        if book is None:
            if args.dry_run:
                print("Без --selection обычный запуск выполняет только --prepare после указания --book.")
                return 0
            raise ValueError("Перевод не запускается без selection. Укажите --book и --prepare.")
        selection_path = resolve_selection(ROOT, book_dir, args.selection)
        if not selection_path.is_file():
            if args.dry_run:
                print("Не найден model-selection.json: обычный запуск проведёт подготовку, проверит выбор и затем запустит перевод.")
                return 0
            binary = shutil.which("codex")
            if binary is None:
                raise ValueError("Codex CLI не найден. Используйте приложение или установите CLI.")
            validate_binary(binary, sys.platform)
            catalog = load_catalog(catalog_file) if catalog_file else query_catalog(binary, args.timeout)
            book_dir.mkdir(parents=True, exist_ok=True)
            preparation = build_prepare_command(ROOT, config, binary, book, book_dir, catalog, selection_path)
            preparation_code = subprocess.run(preparation, cwd=ROOT, check=False).returncode
            if preparation_code:
                return preparation_code
            if not selection_path.is_file():
                raise ValueError("Подготовительная сессия не сохранила model-selection.json; перевод не запущен.")
        selection = load_selection(selection_path, book,
                                   require_fresh=not (book_dir / "work/state.json").is_file())
        binary = shutil.which("codex")
        if binary:
            validate_binary(binary, sys.platform)
        command = build_command(ROOT, config, binary or "codex", book, book_dir, selection_path, selection)
        if args.dry_run:
            _print_command(command)
            print("Команда не выполнена. Доступ к моделям не проверен.")
            return 0
        if binary is None:
            raise ValueError("Codex CLI не найден. Используйте приложение или установите CLI.")
        book_dir.mkdir(parents=True, exist_ok=True)
        return subprocess.run(command, cwd=ROOT, check=False).returncode
    except (OSError, ValueError, ModelSelectionError, tomllib.TOMLDecodeError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
