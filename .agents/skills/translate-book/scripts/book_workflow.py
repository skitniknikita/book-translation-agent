#!/usr/bin/env python3
"""Local bookkeeping for a model-led translation. Never generates or approves prose."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from book_model_selection import validate_selection

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}\Z")
STAGES = ("language", "meaning", "terminology")
KINDS = {"heading", "paragraph", "quote", "footnote", "list", "table", "image", "caption", "formula", "bibliography"}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(value).hexdigest()


def file_hash(path):
    return digest(Path(path).read_bytes())


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def local_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Путь выходит за папку книги")
    return path


def validate_blocks(blocks):
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("Нужен непустой список исходных блоков")
    seen = set()
    for b in blocks:
        if not isinstance(b, dict) or not ID.fullmatch(str(b.get("id", ""))) or b["id"] in seen:
            raise ValueError("Неверный или повторный ID блока")
        seen.add(b["id"])
        if b.get("kind") not in KINDS or not isinstance(b.get("text"), str) or not b["text"].strip():
            raise ValueError("Нужны тип и непустой текст каждого блока")
        if not isinstance(b.get("section"), str) or not b["section"].strip():
            raise ValueError("Нужен раздел для каждого блока")
        if b.get("complexity", "dense") not in {"dense", "normal", "simple"}:
            raise ValueError("Неизвестная сложность")
        if not isinstance(b.get("term_ids", []), list):
            raise ValueError("term_ids должен быть списком")
    return blocks


class Book:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.work = self.root / "work"
        self.path = self.work / "state.json"
        self.state = read_json(self.path)
        if self.state.get("schema_version") != 2:
            raise ValueError("Нужна новая рабочая папка schema_version=2; прежние книги автоматически не мигрируются")
        self.blocks = validate_blocks(read_json(self.work / "source-blocks.json"))
        if digest(self.blocks) != self.state["blocks_sha256"]:
            raise ValueError("Извлечённый исходник изменён. Нужна явная повторная приёмка, не продолжение старых проверок")
        if file_hash(local_path(self.root, self.state["source"]["path"])) != self.state["source"]["sha256"]:
            raise ValueError("Копия исходника изменена")
        self.by_id = {b["id"]: b for b in self.blocks}

    @classmethod
    def initialize(cls, root, source, blocks, selection=None, order="meaning-first"):
        root = Path(root).resolve()
        source = Path(source).resolve()
        validate_blocks(blocks)
        if order != "meaning-first":
            raise ValueError("Новый порядок включается командой compare-order после сравнения первой главы")
        work = root / "work"
        if (work / "state.json").exists():
            raise ValueError("Книга уже создана; используйте status для продолжения")
        if work.exists() and any(p.name not in {"model-selection.json", "model-catalog.json"} for p in work.iterdir()):
            raise ValueError("Рабочая папка не пуста; существующие файлы не перезаписываются")
        if selection is not None and (work / "model-selection.json").exists():
            if read_json(work / "model-selection.json") != selection:
                raise ValueError("Подготовленный выбор моделей отличается; не перезаписывайте его молча")
        raw = source.read_bytes()
        chosen = selection
        if chosen is None and (work / "model-selection.json").exists():
            chosen = read_json(work / "model-selection.json")
        if chosen is not None and chosen.get("source_sha256") != digest(raw):
            raise ValueError("Подготовленный выбор моделей относится к другому исходнику")
        if chosen is not None:
            validate_selection(chosen, source, require_fresh=True)
        work.mkdir(parents=True, exist_ok=True)
        source_name = "source-original" + source.suffix
        (work / source_name).write_bytes(raw)
        atomic_write(work / "source-blocks.json", blocks)
        if selection is not None and not (work / "model-selection.json").exists():
            atomic_write(work / "model-selection.json", selection)
        atomic_write(work / "state.json", {
            "schema_version": 2, "created_at": now(),
            "source": {"path": "work/" + source_name, "original_path": str(source), "sha256": digest(raw)},
            "blocks_sha256": digest(blocks), "review_order": order,
            "model_selection_sha256": file_hash(work / "model-selection.json") if chosen is not None else None,
            "glossary": None, "chunks": [], "calibration": None, "epub": None,
        })
        return cls(root)

    def save(self):
        self.state["updated_at"] = now()
        atomic_write(self.path, self.state)

    def evidence(self, path):
        p = local_path(self.root, path)
        if not p.is_file() or not p.read_bytes().strip():
            raise ValueError("Нужен непустой файл свидетельства/отчёта внутри книги")
        return {"path": str(p.relative_to(self.root)), "sha256": file_hash(p)}

    def evidence_current(self, evidence):
        try:
            return file_hash(local_path(self.root, evidence["path"])) == evidence["sha256"]
        except (KeyError, OSError, ValueError):
            return False

    def models(self):
        path = self.work / "model-selection.json"
        if file_hash(path) != self.state.get("model_selection_sha256"):
            raise ValueError("Выбор моделей изменён или не закреплён; используйте reselect с обоснованием")
        selection = validate_selection(read_json(path), local_path(self.root, self.state["source"]["path"]), require_fresh=False)
        return selection

    def reselect(self, selection, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Нужна причина нового выбора моделей")
        validate_selection(selection, local_path(self.root, self.state["source"]["path"]), require_fresh=True)
        path = self.work / "model-selection.json"
        if path.exists():
            atomic_write(self.work / "model-history" / (file_hash(path) + ".json"), read_json(path))
        atomic_write(path, selection)
        self.state["model_selection_sha256"] = file_hash(path)
        self.state["model_change_reason"] = reason
        self.state["calibration"] = None
        self.state["order_comparison"] = None
        self.state["review_order"] = "meaning-first"
        self.state["epub"] = None
        self.save()

    def glossary_current(self):
        g = self.state.get("glossary")
        if not g:
            return False
        try:
            return (file_hash(self.root / "00_Глоссарий.md") == g["markdown_sha256"]
                    and file_hash(self.work / "terms.json") == g["terms_file_sha256"]
                    and self.evidence_current(g["evidence"]))
        except OSError:
            return False

    def approve_glossary(self, terms, coverage, evidence, index_complete=True, global_rules=None):
        if sorted(coverage) != sorted(self.by_id) or len(coverage) != len(self.by_id):
            raise ValueError("Исследование должно покрывать все исходные блоки, включая примечания")
        if not isinstance(terms, list):
            raise ValueError("Термины должны быть списком")
        term_ids = set()
        for t in terms:
            if not ID.fullmatch(str(t.get("id", ""))) or t["id"] in term_ids:
                raise ValueError("Неверный или повторный ID термина")
            term_ids.add(t["id"])
            for key in ("source", "sense", "target", "status", "confidence", "rationale"):
                if not isinstance(t.get(key), str) or not t[key].strip():
                    raise ValueError("У термина отсутствует " + key)
            if t["status"] not in {"established", "conventional", "working"}:
                raise ValueError("Неверный статус термина")
            if t["confidence"] not in {"high", "medium", "low"}:
                raise ValueError("Неверная уверенность")
            if not t.get("sources") and not (t["status"] == "working" and t.get("search_log")):
                raise ValueError("Нужно свидетельство источника или безрезультатный поиск с рабочим решением")
            for s in t.get("sources", []):
                for key in ("url", "title", "accessed_at", "locator", "evidence"):
                    if not isinstance(s.get(key), str) or not s[key].strip():
                        raise ValueError("Источник не открыт/не описан: " + key)
                if not s["url"].startswith(("https://", "http://")):
                    raise ValueError("Нужна прямая веб-ссылка на источник")
        for b in self.blocks:
            if set(b.get("term_ids", [])) - term_ids:
                raise ValueError("В блоке указан неизвестный термин")
        proof = self.evidence(evidence)
        md_hash = file_hash(self.root / "00_Глоссарий.md")
        if global_rules is not None and (not isinstance(global_rules, str) or not global_rules.strip()):
            raise ValueError("Общие правила должны быть непустым текстом или null")
        atomic_write(self.work / "terms.json", terms)
        self.state["glossary"] = {
            "markdown_sha256": md_hash, "terms_file_sha256": file_hash(self.work / "terms.json"),
            "index_complete": bool(index_complete), "coverage": list(coverage), "evidence": proof,
            "global_rules": global_rules, "global_sha256": digest(global_rules) if global_rules else md_hash,
            "approved_at": now(),
        }
        atomic_write(self.work / "term-index.json", {t["id"]: {
            "decision_sha256": digest(t), "block_ids": [b["id"] for b in self.blocks if t["id"] in b.get("term_ids", [])]
        } for t in terms})
        self.state["epub"] = None
        self.save()

    def term_subset(self, chunk):
        if not self.glossary_current():
            raise ValueError("Нужен актуальный исследованный глоссарий")
        terms = read_json(self.work / "terms.json")
        ids = {t for ident in chunk["block_ids"] for t in self.by_id[ident].get("term_ids", [])}
        if not self.state["glossary"]["index_complete"]:
            return terms
        return [t for t in terms if t["id"] in ids or t.get("global", False)]

    def calibrate(self, record):
        cases = record.get("cases", [])
        if (record.get("passed") is not True or len(cases) != 2
                or {c.get("kind") for c in cases} != {"ordinary", "difficult"}):
            raise ValueError("Нужны успешные обычный и сложный фрагменты")
        if record.get("observed_model") != self.models()["leader"]["model"]:
            raise ValueError("Калибровку принимает выбранная большая модель")
        if record.get("observed_worker_model") != self.models()["worker"]["model"]:
            raise ValueError("Пробные переводы должен выполнить выбранный малый исполнитель")
        used = set()
        trials = []
        for case in cases:
            ids = case.get("source_ids", [])
            if not ids or len(set(ids)) != len(ids) or set(ids) - self.by_id.keys() or set(ids) & used:
                raise ValueError("Нужны разные непустые диапазоны исходных ID для калибровки")
            used.update(ids)
            if case.get("source_sha256") != digest([self.by_id[i] for i in ids]):
                raise ValueError("Пробный перевод относится к другому исходному тексту")
            draft = self.evidence(case["draft"])
            self.validate_trial(read_json(local_path(self.root, case["draft"])), ids)
            trials.append({"kind": case["kind"], "source_ids": ids, "draft": draft,
                           "worker_evidence": self.evidence(case["worker_evidence"])})
        self.state["calibration"] = {"selection_sha256": file_hash(self.work / "model-selection.json"),
                                     "evidence": self.evidence(record["report"]), "trials": trials,
                                     "model_evidence": self.evidence(record["model_evidence"]), "at": now()}
        self.save()

    def validate_trial(self, trial, ids):
        blocks = trial.get("blocks", [])
        if [b.get("id") for b in blocks] != ids or any(not isinstance(b.get("text"), str) or not b["text"].strip() for b in blocks):
            raise ValueError("Пробный результат не покрывает назначенные исходные блоки")

    def calibration_current(self):
        c = self.state.get("calibration")
        return bool(c and self.evidence_current(c["evidence"])
                    and self.evidence_current(c["model_evidence"])
                    and all(self.evidence_current(t["draft"]) and self.evidence_current(t["worker_evidence"]) for t in c["trials"])
                    and c["selection_sha256"] == file_hash(self.work / "model-selection.json"))

    def compare_order(self, record):
        first_section = self.blocks[0]["section"]
        originals = [b for b in self.blocks if b["section"] == first_section]
        source_hash = digest(originals)
        if record.get("chapter_id") != first_section or record.get("observed_model") != self.models()["leader"]["model"]:
            raise ValueError("Нужна оценка первой главы выбранным руководителем")
        if record.get("source_sha256") != source_hash:
            raise ValueError("Сравнение относится к другой версии первой главы")
        if any(c["translations"] for c in self.state["chunks"] if c["section"] != first_section):
            raise ValueError("Порядок закрепляется до перевода последующих разделов")
        if type(record.get("accepted")) is not bool:
            raise ValueError("Нужно явное решение о результате сравнения")
        evidence = {k: self.evidence(record[k]) for k in ("baseline_report", "candidate_report", "assessment")}
        if len({v["path"] for v in evidence.values()}) != 3:
            raise ValueError("Нужны отдельные результаты двух порядков и их оценка")
        for key, order in (("baseline_report", "meaning-first"), ("candidate_report", "language-first")):
            trial = read_json(local_path(self.root, evidence[key]["path"]))
            if trial.get("source_sha256") != source_hash or trial.get("review_order") != order:
                raise ValueError("Результат сравнения не привязан к исходной главе и порядку проверок")
            self.validate_trial(trial, [b["id"] for b in originals])
        self.state["order_comparison"] = {"chapter_id": record["chapter_id"], "accepted": record["accepted"],
                                           "reports": evidence, "at": now(),
                                           "models": file_hash(self.work / "model-selection.json")}
        self.state["review_order"] = "language-first" if record["accepted"] else "meaning-first"
        self.save()

    def effective_order(self):
        comparison = self.state.get("order_comparison")
        if (self.state["review_order"] == "language-first" and comparison and comparison["accepted"]
                and comparison["models"] == file_hash(self.work / "model-selection.json")
                and all(self.evidence_current(e) for e in comparison["reports"].values())):
            return "language-first"
        return "meaning-first"

    def plan(self):
        if self.state["chunks"]:
            raise ValueError("План уже сохранён; автоматическое переразбиение готовой работы запрещено")
        calibrated = self.state.get("calibration")
        calibrated = bool(calibrated and self.evidence_current(calibrated["evidence"])
                          and calibrated["selection_sha256"] == file_hash(self.work / "model-selection.json"))
        chunks, current, previous = [], [], {}

        def flush():
            if not current:
                return
            sec = current[0]["section"]
            ident = f"part-{len(chunks)+1:04d}"
            chunks.append({"id": ident, "section": sec, "block_ids": [b["id"] for b in current],
                           "depends_on": previous.get(sec), "translations": {}, "reviews": {}, "summary": None})
            previous[sec] = ident
            current.clear()

        for b in self.blocks:
            complexity = b.get("complexity", "dense")
            limit = {"dense": 800, "normal": 1200, "simple": 2000 if calibrated else 1200}[complexity]
            words = sum(len(x["text"].split()) for x in current)
            # Preserve every block; never truncate an oversized paragraph or split a note definition.
            if current and (b["section"] != current[0]["section"] or
                            b.get("break_before", False) or words + len(b["text"].split()) > limit):
                flush()
            current.append(b)
        flush()
        self.state["chunks"] = chunks
        self.save()
        return [{k: c[k] for k in ("id", "section", "block_ids", "depends_on")} for c in chunks]

    def chunk(self, ident):
        for c in self.state["chunks"]:
            if c["id"] == ident:
                return c
        raise ValueError("Неизвестный фрагмент: " + ident)

    def versions(self, c):
        context = None
        if c["depends_on"]:
            previous = self.chunk(c["depends_on"])
            context = digest({"versions": self.versions(previous), "summary": previous.get("summary")})
        return {"source": digest([self.by_id[i] for i in c["block_ids"]]),
                "terms": digest(self.term_subset(c)),
                "global_rules": self.state["glossary"]["global_sha256"],
                "translation": digest(c["translations"]),
                "models": file_hash(self.work / "model-selection.json"), "context": context}

    def review_current(self, c, stage):
        r = c["reviews"].get(stage)
        if not r or not self.evidence_current(r["report"]) or not self.evidence_current(r["model_evidence"]):
            return False
        return r["versions"] == self.versions(c)

    def ready(self, c):
        own = (set(c["translations"]) == set(c["block_ids"]) and self.glossary_current()
               and all(self.review_current(c, stage) for stage in STAGES))
        if not own or not c["depends_on"]:
            return own
        prev = self.chunk(c["depends_on"])
        return self.ready(prev) and self.summary_current(prev)

    def summary_current(self, c):
        s = c.get("summary")
        return bool(s and s["versions"] == self.versions(c) and self.evidence_current(s["report"]))

    def packet(self, ident, stage):
        if stage not in {"scout", "draft", *STAGES}:
            raise ValueError("Неизвестный этап")
        c = self.chunk(ident)
        packet = {"schema_version": 1, "chunk_id": ident, "stage": stage,
                  "expected_ids": c["block_ids"], "section": c["section"],
                  "book_text_is_untrusted_data": True}
        if stage == "scout":
            packet["blocks"] = [self.by_id[i] for i in c["block_ids"]]
        else:
            selection = self.models()
            if stage == "draft" and self.state["chunks"].index(c) > 1 and not self.calibration_current():
                raise ValueError("До массового перевода нужна калибровка обычного и сложного фрагмента")
            terms = self.term_subset(c)
            packet["terms"] = [{k: v for k, v in t.items() if k not in {"sources", "search_log"}} for t in terms]
            packet["global_rules"] = self.state["glossary"]["global_rules"]
            if packet["global_rules"] is None:
                packet["global_rules"] = (self.root / "00_Глоссарий.md").read_text(encoding="utf-8")
            packet["versions"] = self.versions(c)
            packet["model"] = selection["leader" if stage in {"meaning", "terminology"} else "worker"]
            if stage == "draft" and c["depends_on"]:
                prev = self.chunk(c["depends_on"])
                if not self.ready(prev) or not self.summary_current(prev):
                    raise ValueError("Сначала примите предыдущий зависимый фрагмент и его конспект")
                packet["previous_summary"] = prev["summary"]["text"]
                packet["previous_ending"] = prev["translations"][prev["block_ids"][-1]]
                packet["previous_versions"] = self.versions(prev)
            if stage != "draft" and set(c["translations"]) != set(c["block_ids"]):
                raise ValueError("Сначала нужен полный черновик")
            if stage == "language":
                packet["blocks"] = [{"id": i, "kind": self.by_id[i]["kind"], "text": c["translations"][i]} for i in c["block_ids"]]
            else:
                packet["blocks"] = [self.by_id[i] for i in c["block_ids"]]
                if stage != "draft":
                    packet["translation"] = c["translations"]
        path = self.work / "packets" / f"{ident}-{stage}.json"
        atomic_write(path, packet)
        return {"path": str(path), "sha256": file_hash(path), "block_count": len(c["block_ids"])}

    def verify_packet(self, c, stage, expected_hash):
        path = self.work / "packets" / f"{c['id']}-{stage}.json"
        p = read_json(path)
        if file_hash(path) != expected_hash or p.get("versions") != self.versions(c):
            raise ValueError("Результат относится к устаревшему заданию")
        if p.get("previous_versions"):
            prev = self.chunk(c["depends_on"])
            if p["previous_versions"] != self.versions(prev) or not self.ready(prev) or not self.summary_current(prev):
                raise ValueError("Контекст предыдущего фрагмента изменён")
        return p

    def submit(self, ident, result):
        c = self.chunk(ident)
        self.verify_packet(c, "draft", result["packet_sha256"])
        blocks = result.get("blocks", [])
        if [b.get("id") for b in blocks] != c["block_ids"]:
            raise ValueError("Пропущены, повторены или переставлены блоки")
        text = {b["id"]: b.get("text") for b in blocks}
        if any(not isinstance(t, str) or not t.strip() for t in text.values()):
            raise ValueError("Пустой перевод")
        # Exact note labels/links are structural and must survive translation.
        source_notes = Counter(re.findall(r"\[\^([^\]]+)\]", "\n".join(self.by_id[i]["text"] for i in c["block_ids"])))
        target_notes = Counter(re.findall(r"\[\^([^\]]+)\]", "\n".join(text.values())))
        if source_notes != target_notes:
            raise ValueError("Нарушены ссылки/определения сносок")
        c["translations"] = text
        c["reviews"] = {}
        c["summary"] = None
        self.state["epub"] = None
        self.save()

    def apply_changes(self, ident, stage, result):
        c = self.chunk(ident)
        self.verify_packet(c, stage, result["packet_sha256"])
        changes = result.get("changes", [])
        updated = dict(c["translations"])
        seen = set()
        for change in changes:
            i = change["id"]
            if i in seen or i not in updated or updated[i] != change["old"]:
                raise ValueError("Правка не совпадает с текущим текстом или повторяется")
            if not isinstance(change.get("new"), str) or not change["new"].strip():
                raise ValueError("Правка не может удалять блок")
            if Counter(re.findall(r"\[\^([^\]]+)\]", change["old"])) != Counter(re.findall(r"\[\^([^\]]+)\]", change["new"])):
                raise ValueError("Правка меняет сноски")
            updated[i] = change["new"]
            seen.add(i)
        if updated != c["translations"]:
            c["translations"] = updated
            c["summary"] = None
            self.state["epub"] = None
            # Reviews remain as history but no longer match the new version.
            self.save()
        return sorted(seen)

    def record_review(self, ident, record):
        c = self.chunk(ident)
        stage = record["stage"]
        if stage not in STAGES:
            raise ValueError("Неверный вид проверки")
        self.verify_packet(c, stage, record["packet_sha256"])
        if record.get("reviewed_ids") != c["block_ids"] or record.get("issues") != []:
            raise ValueError("Не все блоки проверены или остались нерешённые вопросы")
        role = "leader" if stage in {"meaning", "terminology"} else "worker"
        if record.get("observed_model") != self.models()[role]["model"]:
            raise ValueError("Проверку выполнила не выбранная для роли модель")
        c["reviews"][stage] = {"versions": self.versions(c), "model": record["observed_model"],
                                "report": self.evidence(record["report"]),
                                "model_evidence": self.evidence(record["model_evidence"]), "at": now()}
        self.save()

    def record_summary(self, ident, record):
        c = self.chunk(ident)
        if not self.ready(c) or record.get("observed_model") != self.models()["leader"]["model"]:
            raise ValueError("Конспект принимает руководитель после всех проверок")
        if not isinstance(record.get("text"), str) or not record["text"].strip():
            raise ValueError("Нужен содержательный конспект")
        c["summary"] = {"text": record["text"], "versions": self.versions(c),
                        "report": self.evidence(record["report"]), "at": now()}
        self.save()

    def status(self):
        self.models()
        if not self.glossary_current():
            return {"ready": False, "next": "Исследовать/повторно утвердить глоссарий", "chunks": []}
        order = ("language", "meaning", "terminology") if self.effective_order() == "language-first" else ("meaning", "language", "terminology")
        rows = []
        for c in self.state["chunks"]:
            missing = [s for s in order if not self.review_current(c, s)]
            next_stage = "draft" if set(c["translations"]) != set(c["block_ids"]) else (missing[0] if missing else "accepted")
            rows.append({"id": c["id"], "next": next_stage, "stale_reviews": missing,
                         "summary_current": self.summary_current(c), "depends_on": c["depends_on"]})
        epub = self.state.get("epub")
        epub_current = False
        if epub:
            try:
                epub_current = (file_hash(local_path(self.root, epub["path"])) == epub["sha256"]
                                and epub["input_sha256"] == self.build_fingerprint()
                                and all(self.ready(c) for c in self.state["chunks"])
                                and self.calibration_current())
            except (OSError, KeyError, ValueError):
                pass
        return {"ready": bool(rows) and all(self.ready(c) for c in self.state["chunks"]),
                "calibration_current": self.calibration_current(), "epub_current": epub_current,
                "review_order": self.effective_order(), "chunks": rows}

    def usage(self, record):
        if not isinstance(record.get("task_id"), str) or not record["task_id"].strip():
            raise ValueError("Нужен task_id")
        if record.get("scope") != "task_delta":
            raise ValueError("Принимаются только расходы отдельного задания, не накопительные итоги")
        for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
            v = record.get(field)
            if v is not None and (type(v) is not int or v < 0):
                raise ValueError("Токены должны быть неотрицательным числом или null")
        if record.get("input_tokens") is not None and record.get("cached_input_tokens") is not None and record["cached_input_tokens"] > record["input_tokens"]:
            raise ValueError("Кеш входит во входные токены")
        p = self.work / "usage.jsonl"
        records = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
        for existing in records:
            if existing["task_id"] == record["task_id"]:
                if existing == record:
                    return False
                raise ValueError("Повторный task_id с другими метриками")
        atomic_write(p, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records + [record]))
        return True

    def assemble(self):
        if not self.status()["ready"]:
            raise ValueError("Сначала требуются актуальные проверки всех фрагментов")
        if not self.calibration_current():
            raise ValueError("Не подтверждена калибровка выбранных моделей")
        ids = [i for c in self.state["chunks"] for i in c["block_ids"]]
        if ids != [b["id"] for b in self.blocks]:
            raise ValueError("План не покрывает исходник в точном порядке")
        translated = {i: t for c in self.state["chunks"] for i, t in c["translations"].items()}
        parts, anchors = [], []
        for b in self.blocks:
            text = translated[b["id"]]
            if b["kind"] == "footnote":
                parts.append(text)
            else:
                anchor = "bt-" + b["id"]
                anchors.append(anchor)
                parts.append(f"::: {{#{anchor}}}\n\n{text}\n\n:::")
        target = self.root / "01_Перевод.md"
        assembled = "\n\n".join(parts) + "\n"
        if target.exists() and file_hash(target) != self.state.get("assembly_sha256"):
            raise ValueError("01_Перевод.md содержит внешние правки: перенесите их в блоки и повторите проверки перед сборкой")
        atomic_write(target, assembled)
        self.state["assembly_sha256"] = file_hash(target)
        self.save()
        return target, anchors

    def build(self, output, metadata="metadata.json", css=None):
        from epub_builder import build_epub
        destination = local_path(self.root, output)
        protected = {local_path(self.root, self.state["source"]["path"])}
        if self.state["source"].get("original_path"):
            protected.add(Path(self.state["source"]["original_path"]).resolve())
        if destination in protected:
            raise ValueError("Нельзя перезаписывать оригинал результатом сборки")
        text, anchors = self.assemble()
        result = build_epub(self.root, text, self.root / "00_Глоссарий.md",
                            local_path(self.root, metadata), local_path(self.root, output),
                            local_path(self.root, css) if css else None, expected_ids=anchors)
        self.state["epub"] = {"path": output, "sha256": file_hash(local_path(self.root, output)),
                              "metadata": metadata, "css": css,
                              "validated_at": now(), "checks": result}
        self.state["epub"]["input_sha256"] = self.build_fingerprint()
        self.save()
        return result

    def build_fingerprint(self):
        epub = self.state["epub"]
        resources = {str(p.relative_to(self.root)): file_hash(p) for p in sorted((self.root / "assets").rglob("*")) if p.is_file()}
        for item in epub.get("checks", {}).get("input_resources", []):
            resources[item["path"]] = file_hash(local_path(self.root, item["path"]))
        return digest({"versions": [self.versions(c) for c in self.state["chunks"]],
                       "translation_file": file_hash(self.root / "01_Перевод.md"),
                       "glossary_file": file_hash(self.root / "00_Глоссарий.md"),
                       "metadata": file_hash(local_path(self.root, epub["metadata"])),
                       "css": file_hash(local_path(self.root, epub["css"])) if epub.get("css") else None,
                       "assets": resources})


def bank_merge(path, author, terms):
    """Keep distinct context decisions. This reusable evidence never approves a new book."""
    path = Path(path)
    bank = read_json(path) if path.exists() else {"schema_version": 1, "author": author, "entries": []}
    if bank.get("author") != author:
        raise ValueError("База относится к другому автору")
    known = {digest(t) for t in bank["entries"]}
    for term in terms:
        if digest(term) not in known:
            bank["entries"].append(term)
            known.add(digest(term))
    atomic_write(path, bank)
    return len(bank["entries"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book-dir", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--source", required=True)
    init.add_argument("--blocks", required=True)
    init.add_argument("--selection")
    init.add_argument("--review-order", choices=["meaning-first"], default="meaning-first")
    for name in ("status", "plan", "assemble"):
        commands.add_parser(name)
    glossary = commands.add_parser("glossary")
    glossary.add_argument("--record", required=True)
    for name in ("calibrate", "compare-order", "usage"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--record", required=True)
    reselect = commands.add_parser("reselect")
    reselect.add_argument("--selection", required=True)
    reselect.add_argument("--reason", required=True)
    packet = commands.add_parser("packet")
    packet.add_argument("chunk")
    packet.add_argument("stage", choices=["scout", "draft", *STAGES])
    for name in ("submit", "review", "summary", "patch"):
        cmd = commands.add_parser(name)
        cmd.add_argument("chunk")
        cmd.add_argument("--record", required=True)
        if name == "patch":
            cmd.add_argument("--stage", required=True, choices=STAGES)
    build = commands.add_parser("build")
    build.add_argument("--output", required=True)
    build.add_argument("--metadata", default="metadata.json")
    build.add_argument("--css")
    bank = commands.add_parser("bank")
    bank.add_argument("--path", required=True)
    bank.add_argument("--author", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            book = Book.initialize(args.book_dir, args.source, read_json(args.blocks),
                                   read_json(args.selection) if args.selection else None, args.review_order)
            result = {"state": str(book.path)}
        else:
            book = Book(args.book_dir)
            record = read_json(args.record) if hasattr(args, "record") else None
            if args.command == "glossary":
                result = book.approve_glossary(record["terms"], record["reviewed_ids"], record["report"], record.get("index_complete", False), record.get("global_rules"))
            elif args.command == "packet": result = book.packet(args.chunk, args.stage)
            elif args.command == "submit": result = book.submit(args.chunk, record)
            elif args.command == "review": result = book.record_review(args.chunk, record)
            elif args.command == "summary": result = book.record_summary(args.chunk, record)
            elif args.command == "patch": result = book.apply_changes(args.chunk, args.stage, record)
            elif args.command == "calibrate": result = book.calibrate(record)
            elif args.command == "compare-order": result = book.compare_order(record)
            elif args.command == "reselect": result = book.reselect(read_json(args.selection), args.reason)
            elif args.command == "usage": result = book.usage(record)
            elif args.command == "build": result = book.build(args.output, args.metadata, args.css)
            elif args.command == "bank":
                if not book.glossary_current(): raise ValueError("Сначала утвердите глоссарий")
                result = bank_merge(args.path, args.author, read_json(book.work / "terms.json"))
            else: result = getattr(book, args.command)()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Ошибка: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
