from __future__ import annotations

import importlib.util
import sys
import tarfile
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "build_airgap_transfer_bundle.py"
spec = importlib.util.spec_from_file_location("build_airgap_transfer_bundle", SCRIPT_PATH)
assert spec is not None
bundle = cast(Any, importlib.util.module_from_spec(spec))
assert spec.loader is not None
sys.modules[spec.name] = bundle
spec.loader.exec_module(bundle)


def test_airgap_transfer_bundle_includes_handoff_files_and_excludes_generated(
    tmp_path: Path,
) -> None:
    paths = bundle.prepare_paths(tmp_path, replace=False)

    bundle.copy_project(paths)
    bundle.write_readme(paths, includes_wheelhouse=False, includes_pets=False)
    file_count = bundle.write_manifest(paths)
    archive_hash = bundle.write_archive(paths)

    assert file_count > 0
    assert len(archive_hash) == 64
    assert paths.archive.exists()
    assert (paths.bundle_root / "README.md").exists()
    assert (paths.bundle_root / "docs/operations/llm-target-execution-runbook.md").exists()
    assert (paths.bundle_root / "assets/sprites/codex-default/idle.png").exists()
    assert not (paths.bundle_root / "assets/sprites/company-pet").exists()
    assert not (paths.bundle_root / ".git").exists()
    assert not (paths.bundle_root / ".venv").exists()
    assert not any("__pycache__" in path.parts for path in paths.bundle_root.rglob("*"))

    manifest = paths.manifest.read_text("utf-8")
    assert "docs/operations/llm-target-execution-runbook.md" in manifest
    assert "assets/sprites/codex-default/idle.png" in manifest
    assert "assets/sprites/company-pet" not in manifest

    with tarfile.open(paths.archive, "r:gz") as archive:
        names = set(archive.getnames())

    assert "coding-pet-airgap-transfer/docs/operations/llm-target-execution-runbook.md" in names
    assert "coding-pet-airgap-transfer/assets/sprites/codex-default/idle.png" in names
