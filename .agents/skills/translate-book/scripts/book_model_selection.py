"""Offline-safe validation and discovery of models for one book translation.

The catalog only describes what the local Codex account reports.  It cannot
establish that a model is better, cheaper, or available for inference; those
are explicit, reviewable decisions in a book-scoped selection file.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = 1
CATALOG_MAX_AGE_DAYS = 14
OFFICIAL_MODEL_LIST_DOCS = "https://learn.chatgpt.com/docs/app-server#models"


class ModelSelectionError(ValueError):
    """The local catalog or selection cannot safely route a translation."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def catalog_sha256(catalog: dict[str, Any]) -> str:
    """Hash the capability evidence, independent of collection timestamps."""
    return hashlib.sha256(canonical_json(catalog["models"]).encode("utf-8")).hexdigest()


def _supported_efforts(model: dict[str, Any]) -> set[str]:
    efforts = model.get("supportedReasoningEfforts")
    if not isinstance(efforts, list):
        return set()
    result = set()
    for entry in efforts:
        if isinstance(entry, dict) and isinstance(entry.get("reasoningEffort"), str):
            result.add(entry["reasoningEffort"])
    return result


def model_identifier(model: dict[str, Any]) -> str:
    """The inference identifier is `model`; older catalogs use `id`."""
    value = model.get("model", model.get("id"))
    return value if isinstance(value, str) else ""


def validate_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(catalog, dict):
        raise ModelSelectionError("Каталог моделей должен быть JSON-объектом.")
    if catalog.get("complete") is not True:
        raise ModelSelectionError("Каталог моделей неполный; получите все страницы model/list.")
    models = catalog.get("models")
    if not isinstance(models, list) or not models:
        raise ModelSelectionError("В каталоге нет моделей.")
    seen: set[str] = set()
    routed: set[str] = set()
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str) or not model["id"]:
            raise ModelSelectionError("В каталоге есть модель без корректного id.")
        if model["id"] in seen:
            raise ModelSelectionError(f"Модель {model['id']} повторяется в каталоге.")
        seen.add(model["id"])
        identifier = model_identifier(model)
        if not identifier:
            raise ModelSelectionError(f"Для модели {model['id']} не указан идентификатор inference.")
        if identifier in routed:
            raise ModelSelectionError(f"Идентификатор inference {identifier} повторяется в каталоге.")
        routed.add(identifier)
        if not _supported_efforts(model):
            raise ModelSelectionError(f"Для модели {model['id']} не указаны reasoning efforts.")
    return catalog


def merge_catalog_pages(pages: list[dict[str, Any]], collected_at: str | None = None) -> dict[str, Any]:
    """Turn model/list pages into a complete, portable catalog fixture."""
    if not pages:
        raise ModelSelectionError("Не получено ни одной страницы model/list.")
    models: list[dict[str, Any]] = []
    expected_cursor: str | None = None
    seen_cursors: set[str] = set()
    for index, page in enumerate(pages):
        if not isinstance(page, dict) or not isinstance(page.get("data"), list):
            raise ModelSelectionError("Некорректная страница model/list.")
        if index and expected_cursor is None:
            raise ModelSelectionError("В model/list есть страница после завершающей страницы.")
        supplied_cursor = page.get("requestCursor")
        if index and supplied_cursor not in {None, expected_cursor}:
            raise ModelSelectionError("Страницы model/list собраны не в порядке cursor.")
        models.extend(model for model in page["data"] if model.get("hidden") is not True)
        next_cursor = page.get("nextCursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ModelSelectionError("Некорректный nextCursor в model/list.")
        if next_cursor is not None:
            if next_cursor in seen_cursors:
                raise ModelSelectionError("model/list вернул повторяющийся cursor.")
            seen_cursors.add(next_cursor)
        expected_cursor = next_cursor
    if expected_cursor is not None:
        raise ModelSelectionError("Не все страницы model/list были получены.")
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "collected_at": collected_at or datetime.now(timezone.utc).isoformat(),
        "complete": True,
        "source": {"kind": "app-server:model/list", "url": OFFICIAL_MODEL_LIST_DOCS},
        "models": models,
    }
    return validate_catalog(catalog)


def load_catalog(path: Path) -> dict[str, Any]:
    """Read an offline fixture: normalized catalog, pages, or one raw response."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelSelectionError(f"Не удалось прочитать каталог моделей: {path}") from error
    if isinstance(raw, dict) and isinstance(raw.get("pages"), list):
        return merge_catalog_pages(raw["pages"], raw.get("collected_at"))
    if isinstance(raw, dict) and "data" in raw:
        return merge_catalog_pages([raw], raw.get("collected_at"))
    return validate_catalog(raw)


class _JsonlSession:
    """Small bounded JSONL client for the local app-server protocol."""

    def __init__(self, command: list[str], timeout: float) -> None:
        self.timeout = timeout
        self.deadline = time.monotonic() + timeout
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace",
            )
        except OSError as error:
            raise ModelSelectionError("Не удалось запустить локальный Codex app-server.") from error
        self.messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self.messages.put(message)
        self.messages.put(None)

    def request(self, message: dict[str, Any]) -> dict[str, Any]:
        if self.process.stdin is None:
            raise ModelSelectionError("Локальный Codex app-server не принял запрос.")
        try:
            self.process.stdin.write(canonical_json(message) + "\n")
            self.process.stdin.flush()
        except OSError as error:
            raise ModelSelectionError("Локальный Codex app-server закрыл соединение.") from error
        request_id = message.get("id")
        while True:
            try:
                response = self.messages.get(timeout=max(0, self.deadline - time.monotonic()))
            except queue.Empty as error:
                raise ModelSelectionError("Истекло время ожидания model/list; app-server остановлен.") from error
            if response is None:
                raise ModelSelectionError("Локальный Codex app-server завершился до ответа model/list.")
            if response.get("id") == request_id:
                if "error" in response:
                    raise ModelSelectionError("Локальный Codex app-server отклонил model/list.")
                result = response.get("result")
                if not isinstance(result, dict):
                    raise ModelSelectionError("Некорректный ответ model/list.")
                return result

    def close(self) -> None:
        try:
            if self.process.stdin:
                self.process.stdin.close()
        except OSError:
            pass
        if self.process.poll() is None:
            try:
                self.process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                try:
                    self.process.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        try:
            if self.process.stdout:
                self.process.stdout.close()
            self.reader.join(timeout=1)
        except (OSError, ValueError):
            pass


def query_catalog(binary: str, timeout: float = 8.0) -> dict[str, Any]:
    """Read every app-server model/list page; this sends no inference request."""
    session = _JsonlSession([binary, "app-server"], timeout)
    try:
        session.request({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "book_translation", "version": "1"},
        }})
        # JSON-RPC notification: app-server requires it before model/list.
        if session.process.stdin is None:
            raise ModelSelectionError("Локальный Codex app-server закрыл соединение.")
        session.process.stdin.write(canonical_json({"method": "initialized", "params": {}}) + "\n")
        session.process.stdin.flush()
        pages: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        request_id = 2
        while True:
            params: dict[str, Any] = {"limit": 20, "includeHidden": False}
            if cursor is not None:
                params["cursor"] = cursor
            page = session.request({"id": request_id, "method": "model/list", "params": params})
            page["requestCursor"] = cursor
            pages.append(page)
            cursor = page.get("nextCursor")
            if cursor is None:
                break
            if not isinstance(cursor, str) or cursor in seen_cursors:
                raise ModelSelectionError("model/list вернул повторяющийся или некорректный cursor.")
            seen_cursors.add(cursor)
            request_id += 1
        return merge_catalog_pages(pages)
    finally:
        session.close()


def _parse_time(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ModelSelectionError(f"В selection нет даты {label}.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ModelSelectionError(f"Некорректная дата {label}.") from error
    if parsed.tzinfo is None:
        raise ModelSelectionError(f"Дата {label} должна содержать часовой пояс.")
    return parsed.astimezone(timezone.utc)


def _require_evidence(role: dict[str, Any], expected_role: str) -> None:
    classification = role.get("classification")
    if not isinstance(classification, dict) or classification.get("role") != expected_role:
        raise ModelSelectionError(f"Для {expected_role} нужна явная классификация роли.")
    if not isinstance(classification.get("basis"), str) or not classification["basis"].strip():
        raise ModelSelectionError(f"Для {expected_role} не указано обоснование классификации.")
    evidence = classification.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ModelSelectionError(f"Для {expected_role} нужны явные свидетельства выбора.")
    for item in evidence:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip()
                                                  for key in ("kind", "source", "summary")):
            raise ModelSelectionError(f"Некорректное свидетельство выбора {expected_role}.")
    if not any(_is_official_model_page(item["source"]) for item in evidence):
        raise ModelSelectionError(f"Для {expected_role} нужна ссылка на официальную страницу модели.")


def _is_official_model_page(value: str) -> bool:
    parsed = urlparse(value)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (host == "openai.com" or host.endswith(".openai.com")) and bool(parsed.path.strip("/"))


def _validate_timestamp_freshness(value: Any, label: str, now: datetime, require_fresh: bool) -> None:
    stamp = _parse_time(value, label)
    if stamp > now + timedelta(minutes=5):
        raise ModelSelectionError(f"Дата {label} находится в будущем.")
    if require_fresh and now - stamp > timedelta(days=CATALOG_MAX_AGE_DAYS):
        raise ModelSelectionError(
            f"Для новой книги {label} должен быть не старше {CATALOG_MAX_AGE_DAYS} дней."
        )


def validate_selection(selection: dict[str, Any], book: Path, *, require_fresh: bool) -> dict[str, Any]:
    if not isinstance(selection, dict) or selection.get("schema_version") != SCHEMA_VERSION:
        raise ModelSelectionError("Нужен model-selection.json поддерживаемой версии.")
    source = selection.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        raise ModelSelectionError("Selection привязан к другому пути исходника.")
    actual_source_sha = sha256_file(book)
    if source.get("sha256") != actual_source_sha or selection.get("source_sha256") != actual_source_sha:
        raise ModelSelectionError("Хеш исходника не совпадает с model-selection.json.")
    catalog = validate_catalog(selection.get("catalog"))
    if selection.get("catalog_sha256") != catalog_sha256(catalog):
        raise ModelSelectionError("Хеш записанного каталога моделей не совпадает.")
    now = datetime.now(timezone.utc)
    _validate_timestamp_freshness(selection.get("selected_at"), "selected_at", now, require_fresh)
    _validate_timestamp_freshness(catalog.get("collected_at"), "catalog.collected_at", now, require_fresh)
    sources = selection.get("sources")
    if (not isinstance(sources, list)
            or not any(isinstance(item, dict) and item.get("url") == OFFICIAL_MODEL_LIST_DOCS
                       and isinstance(item.get("accessed_at"), str) and item["accessed_at"].strip()
                       for item in sources)):
        raise ModelSelectionError("Selection должен ссылаться на официальную документацию model/list.")
    if selection.get("account_access") != "not_verified_by_catalog":
        raise ModelSelectionError("Selection не должен выдавать каталог за проверку доступа к inference.")
    if not isinstance(selection.get("rationale"), str) or not selection["rationale"].strip():
        raise ModelSelectionError("В selection отсутствует обоснование распределения моделей.")
    by_identifier = {model_identifier(model): model for model in catalog["models"]
                     if model.get("hidden") is not True}
    for role_name in ("leader", "worker"):
        role = selection.get(role_name)
        if not isinstance(role, dict) or not isinstance(role.get("model"), str) or not isinstance(role.get("reasoning_effort"), str):
            raise ModelSelectionError(f"В selection отсутствует модель или reasoning для {role_name}.")
        _require_evidence(role, role_name)
        model = by_identifier.get(role["model"])
        if model is None:
            raise ModelSelectionError(f"Модель {role['model']} для {role_name} отсутствует в записанном каталоге.")
        if role["reasoning_effort"] not in _supported_efforts(model):
            raise ModelSelectionError(f"Reasoning {role['reasoning_effort']} не поддерживается моделью {role['model']}.")
    if selection["leader"]["model"] == selection["worker"]["model"]:
        raise ModelSelectionError("Руководитель и исполнитель должны быть разными выбранными моделями.")
    return selection


def load_selection(path: Path, book: Path, *, require_fresh: bool) -> dict[str, Any]:
    try:
        selection = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelSelectionError(f"Не удалось прочитать model-selection.json: {path}") from error
    return validate_selection(selection, book, require_fresh=require_fresh)
