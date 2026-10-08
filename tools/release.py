#!/usr/bin/env python3
"""Create and verify a deliberately small, allowlisted release archive."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = "release-files.txt"
MANIFEST = "MANIFEST.sha256"
ARCHIVE_ROOT = "book-translation-agent"
PRIVATE_PARTS = {".git", ".env", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "books", "private", "work"}
PRIVATE_NAMES = {".DS_Store", "auth.json", "01_Перевод.md", "01_Translation.md"}
PRIVATE_SUFFIXES = {".epub", ".pdf", ".mobi", ".azw", ".azw3", ".docx", ".odt", ".pem", ".key", ".pyc"}


class ReleaseError(ValueError):
    pass


def _relative_path(value: str) -> PurePosixPath:
    if not value or value != value.strip() or "\\" in value or (len(value) > 1 and value[1] == ":"):
        raise ReleaseError(f"invalid release path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseError(f"release path must be relative and normalized: {value!r}")
    if path.name == MANIFEST:
        raise ReleaseError(f"{MANIFEST} is generated and cannot be allowlisted")
    if any(part in PRIVATE_PARTS or part in PRIVATE_NAMES or part.startswith(("._", ".env")) for part in path.parts):
        raise ReleaseError(f"private or cache path is not releasable: {value!r}")
    if path.suffix.lower() in PRIVATE_SUFFIXES:
        raise ReleaseError(f"book source path is not releasable: {value!r}")
    return path


def allowlisted_paths(root: Path) -> list[PurePosixPath]:
    source = root / ALLOWLIST
    if not source.is_file() or source.is_symlink():
        raise ReleaseError(f"missing regular {ALLOWLIST}")
    paths: list[PurePosixPath] = []
    seen: set[PurePosixPath] = set()
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        path = _relative_path(line)
        if path in seen:
            raise ReleaseError(f"duplicate release path: {path.as_posix()}")
        seen.add(path)
        paths.append(path)
    if not paths:
        raise ReleaseError(f"{ALLOWLIST} has no release files")
    return paths


def _regular_file(root: Path, relative: PurePosixPath) -> Path:
    root = root.resolve()
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ReleaseError(f"symlink is not releasable: {relative.as_posix()}")
    if not current.is_file():
        raise ReleaseError(f"missing regular release file: {relative.as_posix()}")
    try:
        current.resolve().relative_to(root)
    except ValueError as error:
        raise ReleaseError(f"release path escapes root: {relative.as_posix()}") from error
    return current


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_entries(root: Path) -> dict[PurePosixPath, str]:
    manifest = root / MANIFEST
    if not manifest.is_file() or manifest.is_symlink():
        raise ReleaseError(f"missing regular {MANIFEST}")
    result: dict[PurePosixPath, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            raise ReleaseError("invalid manifest line")
        checksum, name = line[:64], line[66:]
        if checksum.lower() != checksum or any(char not in "0123456789abcdef" for char in checksum):
            raise ReleaseError("invalid manifest SHA-256")
        path = _relative_path(name)
        if path in result:
            raise ReleaseError(f"duplicate manifest path: {path.as_posix()}")
        result[path] = checksum
    if not result:
        raise ReleaseError("manifest has no entries")
    return result


def update_manifest(root: Path = ROOT) -> None:
    root = Path(root).resolve()
    lines = [f"{_sha256(_regular_file(root, path))}  {path.as_posix()}" for path in allowlisted_paths(root)]
    target = root / MANIFEST
    if target.is_symlink():
        raise ReleaseError(f"{MANIFEST} must not be a symlink")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=root, delete=False) as stream:
        stream.write("\n".join(lines) + "\n")
        temporary = Path(stream.name)
    temporary.replace(target)


def check_release(root: Path = ROOT) -> list[PurePosixPath]:
    root = Path(root).resolve()
    allowed = allowlisted_paths(root)
    entries = _manifest_entries(root)
    if set(allowed) != set(entries):
        raise ReleaseError("manifest file set does not match release-files.txt")
    for path in allowed:
        if _sha256(_regular_file(root, path)) != entries[path]:
            raise ReleaseError(f"manifest hash mismatch: {path.as_posix()}")
    return allowed


def build_zip(output: Path, root: Path = ROOT) -> None:
    root = Path(root).resolve()
    allowed = check_release(root)
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() != ".zip":
        raise ReleaseError("archive output must end in .zip")
    inputs = {_regular_file(root, path).resolve() for path in allowed}
    inputs.add((root / MANIFEST).resolve())
    if output in inputs:
        raise ReleaseError("archive output cannot overwrite a release input")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".zip", delete=False) as stream:
            temporary = Path(stream.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in [*allowed, PurePosixPath(MANIFEST)]:
                local = root / Path(*path.parts)
                name = f"{ARCHIVE_ROOT}/{path.as_posix()}"
                archive.write(local, name)
                entry = archive.getinfo(name)
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
        temporary.replace(output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-manifest", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--zip", metavar="PATH")
    args = parser.parse_args(argv)
    if not (args.update_manifest or args.check or args.zip):
        parser.error("choose --update-manifest, --check, or --zip")
    try:
        if args.update_manifest:
            update_manifest()
        if args.check or args.zip:
            check_release()
        if args.zip:
            build_zip(Path(args.zip))
    except (OSError, ReleaseError) as error:
        print(f"release check failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
