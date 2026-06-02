from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_NAME = "coding-pet-airgap-transfer"
INCLUDE_PATHS = (
    ".gitattributes",
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "assets",
    "docs",
    "packaging",
    "requirements",
    "scripts",
    "src",
    "tests",
)
EXCLUDED_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv-test",
    ".venv-wsl",
    ".worktrees",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class BundlePaths:
    bundle_root: Path
    archive: Path
    manifest: Path
    readme: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a clean tarball for direct upload to an air-gapped target server.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where the bundle directory and tarball will be written.",
    )
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        help="Optional offline wheelhouse directory to include at bundle root.",
    )
    parser.add_argument(
        "--pet-staging",
        type=Path,
        help="Optional copied Codex/Petdex pet package staging directory.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing bundle directory or tarball.",
    )
    return parser.parse_args()


def should_skip(path: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    return path.suffix in EXCLUDED_SUFFIXES


def copy_tree(source: Path, target: Path) -> None:
    if source.is_file():
        if should_skip(source.relative_to(REPO_ROOT)):
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return

    for child in source.rglob("*"):
        relative = child.relative_to(source)
        repo_relative = child.relative_to(REPO_ROOT)
        if should_skip(repo_relative):
            continue
        destination = target / relative
        if child.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif child.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, destination)


def safe_source_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def prepare_paths(output_dir: Path, *, replace: bool) -> BundlePaths:
    resolved_output = output_dir.expanduser().resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    bundle_root = resolved_output / DEFAULT_BUNDLE_NAME
    archive = resolved_output / f"{DEFAULT_BUNDLE_NAME}.tar.gz"
    if replace:
        if bundle_root.exists():
            shutil.rmtree(bundle_root)
        if archive.exists():
            archive.unlink()
    elif bundle_root.exists() or archive.exists():
        raise FileExistsError("bundle output already exists; pass --replace to overwrite")
    return BundlePaths(
        bundle_root=bundle_root,
        archive=archive,
        manifest=bundle_root / "TRANSFER_MANIFEST.sha256",
        readme=bundle_root / "TRANSFER_README.md",
    )


def copy_project(paths: BundlePaths) -> None:
    paths.bundle_root.mkdir(parents=True)
    for include in INCLUDE_PATHS:
        source = REPO_ROOT / include
        if not source.exists():
            continue
        copy_tree(source, paths.bundle_root / include)


def copy_optional_directory(source: Path | None, target: Path) -> None:
    if source is None:
        return
    resolved = safe_source_path(source)
    if not resolved.is_dir():
        raise NotADirectoryError(resolved)
    copy_tree(resolved, target)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_bundle_files(bundle_root: Path) -> Iterable[Path]:
    for path in sorted(bundle_root.rglob("*")):
        if path.is_file():
            yield path


def write_readme(paths: BundlePaths, *, includes_wheelhouse: bool, includes_pets: bool) -> None:
    wheelhouse_line = "included" if includes_wheelhouse else "not included"
    pets_line = "included" if includes_pets else "not included"
    paths.readme.write_text(
        "\n".join(
            [
                "# coding-pet airgap transfer bundle",
                "",
                "Upload this directory or tarball to the RHEL 8.10 target server.",
                "",
                "Target execution document:",
                "docs/operations/llm-target-execution-runbook.md",
                "",
                f"wheelhouse: {wheelhouse_line}",
                f"pet staging: {pets_line}",
                "",
                "After upload, verify file integrity with:",
                "",
                "```bash",
                "sha256sum -c TRANSFER_MANIFEST.sha256",
                "```",
                "",
                "Then follow the target execution runbook.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_manifest(paths: BundlePaths) -> int:
    lines: list[str] = []
    file_count = 0
    for path in iter_bundle_files(paths.bundle_root):
        if path == paths.manifest:
            continue
        relative = path.relative_to(paths.bundle_root).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}")
        file_count += 1
    paths.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return file_count


def write_archive(paths: BundlePaths) -> str:
    with tarfile.open(paths.archive, "w:gz") as archive:
        archive.add(paths.bundle_root, arcname=paths.bundle_root.name)
    return sha256_file(paths.archive)


def main() -> None:
    args = parse_args()
    paths = prepare_paths(args.output_dir, replace=args.replace)
    copy_project(paths)
    copy_optional_directory(args.wheelhouse, paths.bundle_root / "wheelhouse")
    copy_optional_directory(args.pet_staging, paths.bundle_root / "downloaded-pets")
    write_readme(
        paths,
        includes_wheelhouse=args.wheelhouse is not None,
        includes_pets=args.pet_staging is not None,
    )
    file_count = write_manifest(paths)
    archive_hash = write_archive(paths)
    print(f"bundle_root={paths.bundle_root}")
    print(f"archive={paths.archive}")
    print(f"archive_sha256={archive_hash}")
    print(f"manifest={paths.manifest}")
    print(f"files={file_count}")


if __name__ == "__main__":
    main()
