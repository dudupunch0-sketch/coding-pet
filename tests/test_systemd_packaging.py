from __future__ import annotations

import tomllib
from pathlib import Path

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
