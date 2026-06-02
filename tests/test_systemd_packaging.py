from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD_DIR = ROOT / "packaging" / "systemd"


def test_user_services_are_source_checkout_configurable() -> None:
    for name in ["coding-pet-daemon.service", "coding-pet-widget.service"]:
        content = (SYSTEMD_DIR / name).read_text("utf-8")

        assert "EnvironmentFile=-%h/.config/coding-pet/service.env" in content
        assert "CODING_PET_REPO" in content
        assert "CODING_PET_PYTHON" in content
        assert "/usr/bin/bash -c" in content
        assert "bash -lc" not in content
        assert "WorkingDirectory=%h/company/coding-pet" not in content


def test_user_target_is_enableable() -> None:
    content = (SYSTEMD_DIR / "coding-pet.target").read_text("utf-8")

    assert "[Install]" in content
    assert "WantedBy=default.target" in content


def test_systemd_env_example_documents_company_server_overrides() -> None:
    example = (SYSTEMD_DIR / "coding-pet.service.env.example").read_text("utf-8")

    assert "CODING_PET_REPO=" in example
    assert "CODING_PET_PYTHON=" in example
    assert "CODING_PET_ASSETS_DIR=" in example


def test_systemd_env_example_is_packaged_as_shared_data() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    shared_data = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["shared-data"]

    assert (
        shared_data["packaging/systemd/coding-pet.service.env.example"]
        == "share/coding-pet/systemd/coding-pet.service.env.example"
    )


def test_operations_docs_and_rhel_constraints_are_packaged_as_shared_data() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    shared_data = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["shared-data"]

    assert shared_data["docs"] == "share/coding-pet/docs"
    assert shared_data["requirements"] == "share/coding-pet/requirements"
    assert (ROOT / "docs" / "operations" / "offline-rhel8-wheelhouse.md").exists()
    assert (ROOT / "docs" / "operations" / "codex-pet-packages.md").exists()
    assert (ROOT / "requirements" / "constraints-rhel8.txt").exists()


def test_systemd_unit_paths_fall_back_to_installed_shared_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import coding_pet.cli as cli

    fake_site_packages = tmp_path / "venv" / "lib" / "python3.12" / "site-packages"
    fake_module = fake_site_packages / "coding_pet" / "cli.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# installed module placeholder\n", encoding="utf-8")
    prefix = tmp_path / "venv"
    shared_systemd_dir = prefix / "share" / "coding-pet" / "systemd"
    shared_systemd_dir.mkdir(parents=True)
    for name in cli.SYSTEMD_UNIT_NAMES:
        (shared_systemd_dir / name).write_text("[Unit]\nDescription=test\n", encoding="utf-8")
    monkeypatch.setattr(cli, "__file__", str(fake_module))
    monkeypatch.setattr(sys, "prefix", str(prefix))

    paths = cli._systemd_unit_paths()

    assert paths == [shared_systemd_dir / name for name in cli.SYSTEMD_UNIT_NAMES]
